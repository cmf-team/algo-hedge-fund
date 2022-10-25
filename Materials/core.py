import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

class Feed:
    def __init__(self, max_len=1000000):
        # self.open = []
        # self.volume = []
        self.close = []
        self.max_len = max_len

    def append_item(self, item):
        # self.open.append(item['Open'])
        # self.volume.append(item['Volume'])
        self.close.append(item['Close'])

        if len(self.close) > self.max_len:
            # self.open = self.open[-max_len // 2:]
            self.close = self.close[-self.max_len // 2:]
            # self.volume = self.open[-max_len // 2:]

    def __len__(self):
        return len(self.close)


class IStrategy:
    def make_decision(self, feeds):
        raise NotImplementedError

    def prepare(self, feeds):
        cur_feeds = {key: Feed() for key in feeds}
        feed_len = len(next(iter(feeds.values())))
        for i in range(feed_len):
            for symbol in feeds:
                cur_feeds[symbol].append_item({'Close': feeds[symbol].close[i]})
            self.make_decision(cur_feeds)

    def get_plot_lines(self):
        return dict()

    def get_plot_points(self):
        return []

    def get_name(self):
        return 'Strategy'


class PlotPoint:
    def __init__(self, tick, value, name):
        self.tick = tick
        self.value = value
        self.name = name


class Position:
    def __init__(self, price, amount, direction, symbol):
        self.price = price
        self.amount = amount
        assert direction == 'long' or direction == 'short'
        self.direction = direction
        self.symbol = symbol


class Backtest():
    def __init__(self, feed_dfs, strategy, comission=0.0004):
        self.feed_dfs = feed_dfs
        self.strategy = strategy
        self.comission = comission

    def _plot_strategy(self):
        lines_list = self.strategy.get_plot_lines()
        points_list = self.strategy.get_plot_points()

        for lines, points in zip(lines_list, points_list):
            plt.figure(figsize=(20, 10))
            for line_name, line in lines.items():
                plt.plot(line, label=line_name)

            point_names = set(point.name for point in points)
            for point_name in point_names:
                plt.scatter(
                    [point.tick for point in points if point.name == point_name],
                    [point.value for point in points if point.name == point_name],
                    label=point_name
                )

            plt.legend()

    def _compute_daily_profit(self, strategy_positions, feeds):
        daily_profit = []
        cur_positions = []
        num_ticks = len(next(iter(feeds.values())).close)
        for tick in range(num_ticks):
            daily_profit.append(0)
            for position in cur_positions:
                if position.direction == 'long':
                    daily_profit[-1] += \
                        position.amount * (feeds[position.symbol].close[tick] - position.price)
                elif position.direction == 'short':
                    daily_profit[-1] += \
                        position.amount * (position.price - feeds[position.symbol].close[tick])

            if tick == 0:
                daily_profit[-1] -= \
                    sum(self.comission * feeds[s].close[tick] * abs(a) for s, a in strategy_positions[tick])
            elif strategy_positions[tick] != strategy_positions[tick - 1]:
                daily_profit[-1] -= \
                    sum(self.comission * feeds[s].close[tick] * abs(a) for s, a in strategy_positions[tick].items()) + \
                    sum(self.comission * feeds[s].close[tick] * abs(a) for s, a in strategy_positions[tick - 1].items())

            cur_positions = []
            for symbol, amount in strategy_positions[tick].items():
                cur_positions.append(Position(
                    price=feeds[symbol].close[tick],
                    amount=abs(amount),
                    direction='long' if amount > 0 else 'short',
                    symbol=symbol
                ))

        return daily_profit

    def _compute_num_trades(self, positions):
        num_trades = 0
        for i in range(len(positions) - 1):
            if positions[i] != positions[i + 1]:
                num_trades += 1
        return num_trades

    def _compute_sortino(self, daily_profit, strategy_positions, cur_feeds):
        max_position = 0
        risk_free_rate = 0.05
        for i in range(len(strategy_positions)):
            cur_position = sum(abs(quantity) * cur_feeds[instrument].close[i] for instrument, quantity in strategy_positions[i].items())
            max_position = max(cur_position, max_position)
        daily_profit = np.array(daily_profit)
        daily_profit = daily_profit / max_position
        vol = daily_profit[daily_profit < 0].std()
        sortino_ratio = (daily_profit.mean() - risk_free_rate / (365 * 60 * 24)) / vol
        return sortino_ratio

    def _compute_return(self, daily_profit, strategy_positions, cur_feeds):
        max_position = 0
        for i in range(len(strategy_positions)):
            cur_position = sum(abs(quantity) * cur_feeds[instrument].close[i] for instrument, quantity in strategy_positions[i].items())
            max_position = max(cur_position, max_position)
        if max_position == 0:
            return 0
        return sum(daily_profit)/max_position * 100

    def _compute_metrics(self, daily_profit, strategy_positions, cur_feeds):
        return {'total_profit': sum(daily_profit), 'num_trades': self._compute_num_trades(strategy_positions), \
                'sortino_ratio':self._compute_sortino(daily_profit, strategy_positions, cur_feeds), 'return, %':self._compute_return(daily_profit, strategy_positions, cur_feeds)}

    def _plot_metrics(self, daily_profit):
        profit = [0]
        for x in daily_profit:
            profit.append(profit[-1] + x)
                
        plt.figure(figsize=(20, 10))
        plt.plot(profit, label='profit')
        plt.legend() 

    def run(self, plot=False, num_ticks=None):
        if num_ticks is None:
            num_ticks = min(df.shape[0] for df in self.feed_dfs.values())
        cur_feeds = {symbol: Feed() for symbol in self.feed_dfs}
        strategy_positions = []

        for tick in tqdm(range(num_ticks)):
            for symbol in self.feed_dfs:
                cur_feeds[symbol].append_item(self.feed_dfs[symbol].iloc[tick])
            position = self.strategy.make_decision(cur_feeds)
            strategy_positions.append(position)

        daily_profit = self._compute_daily_profit(strategy_positions, cur_feeds)
        
        if plot:
            self._plot_metrics(daily_profit)
            self._plot_strategy()

        return self._compute_metrics(daily_profit, strategy_positions, cur_feeds), strategy_positions

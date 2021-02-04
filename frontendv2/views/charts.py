import operator
import datetime
from django.db.models import Q, Count, Max
from django.contrib import messages
from frontendv2 import colors as savannah_colors

class ChartColors(object):
    def __init__(self, colors=None):
        if colors is None:
            self.from_colors = savannah_colors.CHART_COLORS
        else:
            self.from_colors = colors
        self.next_color = 0

    def __iter__(self):
        return self

    def __len__(self):
        return len(self.from_colors)

    def __next__(self):
        color = self.from_colors[self.next_color]
        self.next_color += 1
        if self.next_color >= len(self.from_colors):
            self.next_color = 0 
        return color

    def next(self):
        return next(self)

class Chart(object):
    def __init__(self, id, title=None):
        self.id = id
        if title is not None:
            self.title = title
        else:
            self.title = self.id

class PieChart(Chart):
    def __init__(self, id, title, limit=None):
        super().__init__(id, title)
        self.script_template = 'savannahv2/piechart_script.html'
        self.limit = limit
        self.colors = ChartColors()
        self._raw_data = []
        self._processed_data = None
        self._show_legend = True

    def add(self, data_name, data_value, data_color=None):
        if data_color is None:
            data_color = next(self.colors)
        self._raw_data.append((data_name, data_value, data_color))

    @property
    def show_legend(self, setval=None):
        if self._show_legend:
            return 'true'
        else:
            return 'false'

    def set_show_legend(self, show):
        self._show_legend = show

    @property
    def processed_data(self):
        if self._processed_data is None:
            self._processed_data = self._raw_data
            if self.limit is not None and self.limit > 0 and len(self._processed_data) > self.limit:
                other_count = sum([count for channel, count, color in self._processed_data[self.limit-1:]])
                self._processed_data = self._processed_data[:self.limit-1]
                self._processed_data.append(("Other", other_count, savannah_colors.OTHER))
        return self._processed_data

    def get_data_names(self):
        return str([data[0] for data in self.processed_data])

    def get_data_values(self):
        return [data[1] for data in self.processed_data]

    def get_data_colors(self):
        return ['#'+data[2] for data in self.processed_data]

class FunnelChart(Chart):
    def __init__(self, id, title, stages, colors=None):
        super(FunnelChart, self).__init__(id, title)
        self.script_template = 'savannahv2/funnelchart_script.html'
        self.stages = stages
        self.colors = ChartColors([savannah_colors.LEVEL.CORE, savannah_colors.LEVEL.CONTRIBUTOR, savannah_colors.LEVEL.PARTICIPANT, savannah_colors.LEVEL.VISITOR])
        self._raw_data = dict()
        self._processed_data = None

    def add(self, data_name, data_value):
        self._raw_data[data_name] = data_value

    @property
    def processed_data(self):
        if self._processed_data is None:
            total = 0
            self._processed_data = []
            for name, label in self.stages:
                total += self._raw_data.get(name, 0)
                self._processed_data.append((name, total))
        return self._processed_data

    def get_data_names(self):
        return str([label for name, label in self.stages])

    def get_data_values(self):
        return [data[1] for data in self.processed_data]

    def get_data_colors(self):
        return ['#'+self.colors.next() for i in range(len(self.stages))]
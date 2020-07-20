/*!
 * Chart.Funnel.js
 * A funnel plugin for Chart.js(http://chartjs.org/)
 * Version: 1.1.5
 *
 * Copyright 2016 Jone Casaper & YetiForce
 * Released under the MIT license
 * https://github.com/xch89820/Chart.Funnel.js/blob/master/LICENSE.md
 */
(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}(g.Chart || (g.Chart = {})).Funnel = f()}})(function(){var define,module,exports;return (function(){function r(e,n,t){function o(i,f){if(!n[i]){if(!e[i]){var c="function"==typeof require&&require;if(!f&&c)return c(i,!0);if(u)return u(i,!0);var a=new Error("Cannot find module '"+i+"'");throw a.code="MODULE_NOT_FOUND",a}var p=n[i]={exports:{}};e[i][0].call(p.exports,function(r){var n=e[i][1][r];return o(n||r)},p,p.exports,r,e,n,t)}return n[i].exports}for(var u="function"==typeof require&&require,i=0;i<t.length;i++)o(t[i]);return o}return r})()({1:[function(require,module,exports){

},{}],2:[function(require,module,exports){
/**
 *
 * Main file of Chart.Funnel.js
 * @author Jone Casper
 * @email xu.chenhui@live.com
 *
 */

/* global window */
"use strict";

var Chart = require(1);
Chart = typeof(Chart) === 'function' ? Chart : window.Chart;

require(4)(Chart);
require(3)(Chart);

module.exports = Chart;
},{"1":1,"3":3,"4":4}],3:[function(require,module,exports){
/**
 *
 * Extend funnel Charts
 * @author Jone Casper
 * @email xu.chenhui@live.com
 *
 * @example
 * var data = {
 *  labels: ["A", "B", "C"],
 * 	datasets: [{
 * 	  data: [300, 50, 100],
 * 	  backgroundColor: [
 *       "#FF6384",
 *       "#36A2EB",
 *       "#FFCE56"
 *    ],
 *    hoverBackgroundColor: [
 *        "#FF6384",
 *        "#36A2EB",
 *        "#FFCE56"
 *    ]
 * 	}]
 * }
 *
 */

"use strict";

module.exports = function (Chart) {
	var helpers = Chart.helpers;

	Chart.defaults.funnel = {
		hover: {
			mode: "label"
		},
		sort: 'asc', // sort options: 'asc', 'desc'
		gap: 0,
		bottomWidth: null, // the bottom width of funnel
		topWidth: 0, // the top width of funnel
		keep: 'auto', // Keep left or right
		elements: {
			borderWidth: 0
		},
		tooltips: {
			callbacks: {
				title: function (tooltipItem, data) {
					return '';
				},
				label: function (tooltipItem, data) {
					return data.labels[tooltipItem.index] + ': ' + data.datasets[tooltipItem.datasetIndex].data[tooltipItem.index];
				}
			}
		},
		legendCallback: function (chart) {
			var text = [];
			text.push('<ul class="' + chart.id + '-legend">');

			var data = chart.data;
			var datasets = data.datasets;
			var labels = data.labels;

			if (datasets.length) {
				for (var i = 0; i < datasets[0].data.length; ++i) {
					text.push('<li><span style="background-color:' + datasets[0].backgroundColor[i] + '"></span>');
					if (labels[i]) {
						text.push(labels[i]);
					}
					text.push('</li>');
				}
			}

			text.push('</ul>');
			return text.join("");
		},
		legend: {
			labels: {
				generateLabels: function (chart) {
					var data = chart.data;
					if (data.labels.length && data.datasets.length) {
						return data.labels.map(function (label, i) {
							var meta = chart.getDatasetMeta(0);
							var ds = data.datasets[0];
							var trap = meta.data[i];
							var custom = trap.custom || {};
							var getValueAtIndexOrDefault = helpers.getValueAtIndexOrDefault;
							var trapeziumOpts = chart.options.elements.trapezium;
							var fill = custom.backgroundColor ? custom.backgroundColor : getValueAtIndexOrDefault(ds.backgroundColor, i, trapeziumOpts.backgroundColor);
							var stroke = custom.borderColor ? custom.borderColor : getValueAtIndexOrDefault(ds.borderColor, i, trapeziumOpts.borderColor);
							var bw = custom.borderWidth ? custom.borderWidth : getValueAtIndexOrDefault(ds.borderWidth, i, trapeziumOpts.borderWidth);

							return {
								text: label,
								fillStyle: fill,
								strokeStyle: stroke,
								lineWidth: bw,
								hidden: isNaN(ds.data[i]) || meta.data[i].hidden,

								// Extra data used for toggling the correct item
								index: i,
								// Original Index
								_index: trap._index
							};
						});
					} else {
						return [];
					}
				}
			},

			onClick: function (e, legendItem) {
				var index = legendItem.index;
				var chart = this.chart;
				var i, ilen, meta;

				for (i = 0, ilen = (chart.data.datasets || []).length; i < ilen; ++i) {
					meta = chart.getDatasetMeta(i);
					meta.data[index].hidden = !meta.data[index].hidden;
				}

				chart.update();
			}
		},
		scales: {
			xAxes: [{
					position: 'left',
					type: 'category',
					display: false,
					// Specific to Horizontal Bar Controller
					categoryPercentage: 0.8,
					barPercentage: 0.9,

					// offset settings
					offset: true,

					// grid line settings
					gridLines: {
						offsetGridLines: true
					}
				}],
			yAxes: [{
					position: 'left',
					type: 'category',
					display: false,
					// Specific to Horizontal Bar Controller
					categoryPercentage: 0.8,
					barPercentage: 0.9,

					// offset settings
					offset: true,

					// grid line settings
					gridLines: {
						offsetGridLines: true
					}
				}]
		},
	};

	Chart.controllers.funnel = Chart.DatasetController.extend({

		dataElementType: Chart.elements.Trapezium,

		initialize: function (chart, datasetIndex) {
			Chart.controllers.bar.prototype.initialize.call(this, chart, datasetIndex);
			// sort arrays
			if (typeof chart.options !== 'undefined' && typeof chart.options.sort !== 'undefined' && chart.options.sort.substr(0, 4) !== 'data') {
				var dataset = chart.data.datasets[datasetIndex];
				var dataPositions = [];
				var originalData = dataset.data.slice();
				helpers.each(dataset.data, function (item, index) {
					dataPositions.push({index, value: item});
				});
				dataPositions.sort(function (a, b) {
					return chart.options.sort === 'asc' ? a.value - b.value : b.value - a.value;
				});
				// sort labels in the same manner as data sort order
				var labels = chart.data.labels.map((value, index) => {
					return chart.data.labels[ dataPositions[index].index ];
				});
				chart.data.labels = labels;
				// sort other arrays inside datasets
				var keys = Object.keys(dataset);
				for (var i = 0, len = keys.length; i < len; i++) {
					var key = keys[i];
					var arr = dataset[key];
					if (dataset.hasOwnProperty(key) && Array.isArray(arr)) {
						var sortedArr = arr.map((item, index) => {
							return arr[dataPositions[index].index];
						});
						dataset[key] = sortedArr;
					}
				}
			}
		},

		linkScales: function () {
			var me = this;
			var meta = me.getMeta();
			var dataset = me.getDataset();
			if (meta.yAxisID === null || !(meta.yAxisID in me.chart.scales)) {
				meta.yAxisID = dataset.yAxisID || me.chart.options.scales.yAxes[0].id;
			}
			if (meta.xAxisID === null || !(meta.xAxisID in me.chart.scales)) {
				meta.xAxisID = dataset.xAxisID || me.chart.options.scales.xAxes[0].id;
			}
		},

		update: function update(reset) {
			var me = this;
			var chart = me.chart,
					chartArea = chart.chartArea,
					opts = chart.options,
					meta = me.getMeta(),
					elements = meta.data,
					borderWidth = opts.elements.borderWidth || 0,
					availableWidth = chartArea.right - chartArea.left - borderWidth * 2,
					availableHeight = chartArea.bottom - chartArea.top - borderWidth * 2;

			// top and bottom width
			var bottomWidth = availableWidth,
					topWidth = (opts.topWidth < availableWidth ? opts.topWidth : availableWidth) || 0;
			if (opts.bottomWidth) {
				bottomWidth = opts.bottomWidth < availableWidth ? opts.bottomWidth : availableWidth;
			}

			// percentage calculation and sort data
			var dataset = me.getDataset(),
					valAndLabels = [],
					visiableNum = 0,
					dMax = 0;
			helpers.each(dataset.data, function (val, index) {
				var backgroundColor = helpers.getValueAtIndexOrDefault(dataset.backgroundColor, index),
						hidden = elements[index].hidden;
				valAndLabels.push({
					hidden: hidden,
					orgIndex: index,
					val: val,
					backgroundColor: backgroundColor,
					borderColor: helpers.getValueAtIndexOrDefault(dataset.borderColor, index, backgroundColor),
					label: helpers.getValueAtIndexOrDefault(dataset.label, index, chart.data.labels[index])
				});
				if (!elements[index].hidden) {
					visiableNum++;
					dMax = val > dMax ? val : dMax;
				}
			});
			var dwRatio = bottomWidth / dMax;
			// For render hidden view
			var _viewIndex = 0;
			helpers.each(valAndLabels, function (dal, index) {
				dal._viewIndex = !dal.hidden ? _viewIndex++ : -1;
			});
			// Elements height calculation
			var gap = opts.gap || 0,
					elHeight = (availableHeight - ((visiableNum - 1) * gap)) / visiableNum;

			// save
			me.topWidth = topWidth;
			me.dwRatio = dwRatio;
			me.elHeight = elHeight;
			me.valAndLabels = valAndLabels;
			helpers.each(elements, function (trapezium, index) {
				me.updateElement(trapezium, index, reset);
			}, me);
		},

		// update elements
		updateElement: function updateElement(trapezium, index, reset) {
			var me = this,
					chart = me.chart,
					chartArea = chart.chartArea,
					opts = chart.options,
					sort = opts.sort,
					dwRatio = me.dwRatio,
					elHeight = me.elHeight,
					gap = opts.gap || 0,
					borderWidth = opts.elements.borderWidth || 0;

			// calculate x,y,base, width,etc.
			var x, y, x1, x2,
					elementType = 'isosceles',
					elementData = me.valAndLabels[index], upperWidth, bottomWidth,
					viewIndex = elementData._viewIndex < 0 ? index : elementData._viewIndex,
					base = chartArea.top + (viewIndex + 1) * (elHeight + gap) - gap;

			var meta = me.getMeta();
			trapezium._xScale = me.getScaleForId(meta.xAxisID);

			if (sort === 'asc' || sort === 'data-asc' || !sort) {
				// Find previous element which is visible
				var previousElement = helpers.findPreviousWhere(me.valAndLabels,
						function (el) {
							return !el.hidden;
						},
						index
						);
				upperWidth = previousElement ? previousElement.val * dwRatio : me.topWidth;
				bottomWidth = elementData.val * dwRatio;
			} else if (sort === 'desc' || sort === 'data-desc') {
				var nextElement = helpers.findNextWhere(me.valAndLabels,
						function (el) {
							return !el.hidden;
						},
						index
						);
				upperWidth = elementData.val * dwRatio;
				bottomWidth = nextElement ? nextElement.val * dwRatio : me.topWidth;
			}

			y = chartArea.top + elementData.orgIndex * (elHeight + gap);
			if (opts.keep === 'left') {
				elementType = 'scalene';
				x1 = chartArea.left + upperWidth / 2;
				x2 = chartArea.left + bottomWidth / 2;
				x = x1;
			} else if (opts.keep === 'right') {
				elementType = 'scalene';
				x1 = chartArea.right - upperWidth / 2;
				x2 = chartArea.right - bottomWidth / 2;
				x = x1;
			} else {
				x = (chartArea.left + chartArea.right) / 2;
			}

			helpers.extend(trapezium, {
				// Utility
				_datasetIndex: me.index,
				_index: elementData.orgIndex,

				// Desired view properties
				_model: {
					type: elementType,
					y: y,
					base: base > chartArea.bottom ? chartArea.bottom : base,
					x: x,
					x1: x1,
					x2: x2,
					upperWidth: (reset || !!elementData.hidden) ? 0 : upperWidth,
					bottomWidth: (reset || !!elementData.hidden) ? 0 : bottomWidth,
					borderWidth: borderWidth,
					backgroundColor: elementData && elementData.backgroundColor,
					borderColor: elementData && elementData.borderColor,
					label: elementData && elementData.label
				}
			});
			trapezium.pivot();
		},
		removeHoverStyle: function (trapezium) {
			Chart.DatasetController.prototype.removeHoverStyle.call(this, trapezium, this.chart.options.elements.trapezium);
		}
	});
};

},{}],4:[function(require,module,exports){
/**
 *
 * Extend trapezium element
 * @author Jone Casper
 * @email xu.chenhui@live.com
 *
 */

"use strict";

module.exports = function (Chart) {
	var helpers = Chart.helpers,
			globalOpts = Chart.defaults.global;

	globalOpts.elements.trapezium = {
		backgroundColor: globalOpts.defaultColor,
		borderWidth: 0,
		borderColor: globalOpts.defaultColor,
		borderSkipped: 'bottom',
		type: 'isosceles'  // isosceles, scalene
	};

	// Thanks for https://github.com/substack/point-in-polygon
	var pointInPolygon = function (point, vs) {
		// ray-casting algorithm based on
		// http://www.ecse.rpi.edu/Homepages/wrf/Research/Short_Notes/pnpoly.html

		var x = point[0], y = point[1];

		var inside = false;
		for (var i = 0, j = vs.length - 1; i < vs.length; j = i++) {
			var xi = vs[i][0], yi = vs[i][1];
			var xj = vs[j][0], yj = vs[j][1];

			var intersect = ((yi > y) != (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
			if (intersect)
				inside = !inside;
		}

		return inside;
	};

	Chart.elements.Trapezium = Chart.elements.Rectangle.extend({
		getCorners: function () {
			var vm = this._view;
			var globalOptionTrapeziumElements = globalOpts.elements.trapezium;

			var corners = [],
					type = vm.type || globalOptionTrapeziumElements.type,
					top = vm.y,
					borderWidth = vm.borderWidth || globalOptionTrapeziumElements.borderWidth,
					upHalfWidth = vm.upperWidth / 2,
					botHalfWidth = vm.bottomWidth / 2,
					halfStroke = borderWidth / 2;

			halfStroke = halfStroke < 0 ? 0 : halfStroke;

			// An isosceles trapezium
			if (type == 'isosceles') {
				var x = vm.x;

				// Corner points, from bottom-left to bottom-right clockwise
				// | 1 2 |
				// | 0 3 |
				corners = [
					[x - botHalfWidth + halfStroke, vm.base],
					[x - upHalfWidth + halfStroke, top + halfStroke],
					[x + upHalfWidth - halfStroke, top + halfStroke],
					[x + botHalfWidth - halfStroke, vm.base]
				];
			} else if (type == 'scalene') {
				var x1 = vm.x1,
						x2 = vm.x2;

				corners = [
					[x2 - botHalfWidth + halfStroke, vm.base],
					[x1 - upHalfWidth + halfStroke, top + halfStroke],
					[x1 + upHalfWidth - halfStroke, top + halfStroke],
					[x2 + botHalfWidth - halfStroke, vm.base]
				];
			}


			return corners;
		},
		draw: function () {
			var ctx = this._chart.ctx;
			var vm = this._view;
			var globalOptionTrapeziumElements = globalOpts.elements.trapezium;

			var corners = this.getCorners();
			this._cornersCache = corners;

			ctx.beginPath();
			ctx.fillStyle = vm.backgroundColor || globalOptionTrapeziumElements.backgroundColor;
			ctx.strokeStyle = vm.borderColor || globalOptionTrapeziumElements.borderColor;
			ctx.lineWidth = vm.borderWidth || globalOptionTrapeziumElements.borderWidth;

			// Find first (starting) corner with fallback to 'bottom'
			var borders = ['bottom', 'left', 'top', 'right'];
			var startCorner = borders.indexOf(
					vm.borderSkipped || globalOptionTrapeziumElements.borderSkipped,
					0);
			if (startCorner === -1)
				startCorner = 0;

			function cornerAt(index) {
				return corners[(startCorner + index) % 4];
			}

			// Draw rectangle from 'startCorner'
			ctx.moveTo.apply(ctx, cornerAt(0));
			for (var i = 1; i < 4; i++)
				ctx.lineTo.apply(ctx, cornerAt(i));

			ctx.fill();
			if (vm.borderWidth) {
				ctx.stroke();
			}
		},
		height: function () {
			var vm = this._view;
			if (!vm) {
				return 0;
			}

			return vm.base - vm.y;
		},
		inRange: function (mouseX, mouseY) {
			var vm = this._view;
			if (!vm) {
				return false;
			}
			var corners = this._cornersCache ? this._cornersCache : this.getCorners();
			return pointInPolygon([mouseX, mouseY], corners);
		},
		inLabelRange: function (mouseX) {
			var x,
					vm = this._view;

			if (!vm) {
				return false;
			}

			if (vm.type == 'scalene') {
				if (vm.x1 > vm.x2) {
					return mouseX >= vm.x2 - vm.bottomWidth / 2 && mouseX <= vm.x1 + vm.upperWidth / 2;
				} else {
					return mouseX <= vm.x2 + vm.bottomWidth / 2 && mouseX >= vm.x1 - vm.upperWidth / 2;
				}
			}

			var maxWidth = Math.max(vm.upperWidth, vm.bottomWidth);
			return mouseX >= vm.x - maxWidth / 2 && mouseX <= vm.x + maxWidth / 2;
		},
		tooltipPosition: function () {
			var vm = this._view;
			return {
				x: vm.x || vm.x2,
				y: vm.base - (vm.base - vm.y) / 2
			};
		},
		getArea: function () {
			var vm = this._view;
			var total = 0;
			var corners = this._cornersCache ? this._cornersCache : this.getCorners();
			for (var i = 0, l = corners.length; i < l; i++) {
				var addX = corners[i][0];
				var addY = corners[i == corners.length - 1 ? 0 : i + 1][1];
				var subX = corners[i == corners.length - 1 ? 0 : i + 1][0];
				var subY = corners[i][1];
				total += (addX * addY * 0.5);
				total -= (subX * subY * 0.5);
			}
			return Math.abs(total);
		},
		getCenterPoint: function () {
			var corners = this._cornersCache ? this._cornersCache : this.getCorners();
			var vm = this._view;
			var x = 0, y = 0, i, j, f, point1, point2;
			for (i = 0, j = corners.length - 1; i < corners.length; j = i, i++) {
				point1 = corners[i];
				point2 = corners[j];
				f = point1[0] * point2[1] - point2[0] * point1[1];
				x += (point1[0] + point2[0]) * f;
				y += (point1[1] + point2[1]) * f;
			}
			f = this.getArea() * 6;
			return {x: x / f, y: y / f};
		},
	});
};

},{}]},{},[2])(2)
});

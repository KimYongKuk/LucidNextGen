'use client';

import { useMemo } from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  AreaChart,
  Area,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';

export interface ChartData {
  success: boolean;
  type: 'chart_data';
  chart_type: 'line' | 'bar' | 'pie' | 'combo' | 'stacked_bar' | 'area';
  title: string;
  data: Array<Record<string, unknown>>;
  config: {
    xKey?: string;
    yKey?: string;
    yKeys?: string[];
    colors?: string[];
    horizontal?: boolean;
    barKeys?: string[];
    lineKeys?: string[];
    barColors?: string[];
    lineColors?: string[];
    stackKeys?: string[];
    areaKeys?: string[];
  };
}

interface ChartDisplayProps {
  chartData: ChartData;
}

export function ChartDisplay({ chartData }: ChartDisplayProps) {
  const { chart_type, title, data, config } = chartData;

  const renderChart = useMemo(() => {
    switch (chart_type) {
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                dataKey={config.xKey}
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <YAxis
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
              {config.yKeys?.map((key, idx) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={config.colors?.[idx] || '#4A90D9'}
                  strokeWidth={2}
                  dot={{ fill: config.colors?.[idx] || '#4A90D9', strokeWidth: 2, r: 4 }}
                  activeDot={{ r: 6 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={data}
              layout={config.horizontal ? 'vertical' : 'horizontal'}
              margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              {config.horizontal ? (
                <>
                  <XAxis type="number" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
                  <YAxis
                    dataKey={config.xKey}
                    type="category"
                    tick={{ fill: '#9CA3AF', fontSize: 12 }}
                    width={80}
                  />
                </>
              ) : (
                <>
                  <XAxis dataKey={config.xKey} tick={{ fill: '#9CA3AF', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#9CA3AF', fontSize: 12 }} />
                </>
              )}
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Bar
                dataKey={config.yKey}
                fill={config.colors?.[0] || '#4A90D9'}
                radius={[4, 4, 0, 0]}
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={`hsl(210, 70%, ${45 + index * 5}%)`}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );

      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={350}>
            <PieChart margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent = 0 }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                outerRadius={120}
                fill="#4A90D9"
                dataKey="value"
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={config.colors?.[index % (config.colors?.length || 10)] || '#4A90D9'}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
            </PieChart>
          </ResponsiveContainer>
        );

      case 'combo':
        return (
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey={config.xKey} tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <YAxis yAxisId="left" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
              {config.barKeys?.map((key, idx) => (
                <Bar
                  key={key}
                  yAxisId="left"
                  dataKey={key}
                  fill={config.barColors?.[idx] || '#4A90D9'}
                  radius={[4, 4, 0, 0]}
                />
              ))}
              {config.lineKeys?.map((key, idx) => (
                <Line
                  key={key}
                  yAxisId="right"
                  type="monotone"
                  dataKey={key}
                  stroke={config.lineColors?.[idx] || '#E74C3C'}
                  strokeWidth={2}
                  dot={{ fill: config.lineColors?.[idx] || '#E74C3C', strokeWidth: 2, r: 4 }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        );

      case 'stacked_bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey={config.xKey} tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
              {config.stackKeys?.map((key, idx) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId="a"
                  fill={config.colors?.[idx] || '#4A90D9'}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );

      case 'area':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey={config.xKey} tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F3F4F6',
                }}
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
              {config.areaKeys?.map((key, idx) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={config.colors?.[idx] || '#4A90D9'}
                  fill={config.colors?.[idx] || '#4A90D9'}
                  fillOpacity={0.3}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        );

      default:
        return <div className="text-gray-400">지원하지 않는 차트 타입입니다.</div>;
    }
  }, [chart_type, data, config]);

  return (
    <div className="my-4 rounded-lg border border-gray-700 bg-gray-800/50 p-4">
      <h3 className="mb-4 text-center text-lg font-semibold text-gray-200">{title}</h3>
      {renderChart}
    </div>
  );
}

// 문자열에서 차트 데이터 파싱 시도
export function tryParseChartData(content: string): ChartData | null {
  try {
    // JSON 형태의 차트 데이터 찾기
    const jsonMatch = content.match(/\{[\s\S]*"type"\s*:\s*"chart_data"[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      if (parsed.type === 'chart_data' && parsed.success) {
        return parsed as ChartData;
      }
    }
    return null;
  } catch {
    return null;
  }
}
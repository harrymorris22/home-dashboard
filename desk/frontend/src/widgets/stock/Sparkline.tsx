/** Pure SVG sparkline. No recharts dep (kept the tile bundle light).
 * Draws min→max scaled polyline of the provided values. */
export function Sparkline({
  values,
  width = 120,
  height = 40,
  stroke = "#0E1016",
  strokeWidth = 1.5,
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  strokeWidth?: number;
}) {
  if (!values || values.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;

  const points = values
    .map((v, i) => {
      const x = (i * step).toFixed(1);
      const y = (height - ((v - min) / range) * height).toFixed(1);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} aria-hidden="true">
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

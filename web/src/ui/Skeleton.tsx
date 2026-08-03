export default function Skeleton({
  width = '100%',
  height = 16,
  radius,
  className = '',
  style,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number | string;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ display: 'block', width, height, borderRadius: radius, ...style }}
    />
  );
}

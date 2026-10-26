export default function Icon({ name, size = 20, className = '' }) {
  return (
    <span
      className={`icon ${className}`}
      aria-hidden="true"
      style={{ width: size, height: size, '--icon': `url(/icons/${name}.png)` }}
    />
  )
}

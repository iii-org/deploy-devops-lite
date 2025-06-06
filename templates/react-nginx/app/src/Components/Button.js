export function Button({ onClick, className, title }) {
  return (
    <button className={className} type="button" onClick={onClick}>
      {title}
    </button>
  )
}

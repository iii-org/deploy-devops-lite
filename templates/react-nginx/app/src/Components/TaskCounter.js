export function TaskCounter({ tasks }) {
  return (
    <span className="total-tasks">
      <strong>{tasks}</strong> tasks registered.
    </span>
  )
}

import { TableRow } from './TableRow'
import './table.css'

export function Table({ tasks, removeTask }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Description</th>
          <th>Start Date</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((task) => (
          <TableRow key={task.id} task={task} removeTask={removeTask} />
        ))}
      </tbody>
    </table>
  )
}

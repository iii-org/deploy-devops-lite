import { FaTrash } from 'react-icons/fa'

export function TableRow({ task, removeTask }) {
  return (
    <tr>
      <td>{task.description}</td>
      <td>{task.date}</td>
      <td onClick={() => removeTask(task.id)}>
        <FaTrash size={20} color="#De3F4E" className="icon-delete" />
      </td>
    </tr>
  )
}

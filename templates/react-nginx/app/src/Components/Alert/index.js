import { FiX } from 'react-icons/fi'
import './alert.css'

export function Alert({ message, closeAlert }) {
  return (
    <div className="alert-container">
      <header className="alert-header">
        <h2 className="alert-title">Ops...</h2>
        <FiX size={20} color="FFF" className="alert-icon" onClick={() => closeAlert(false)} />
      </header>

      <p className="alert-message">{message}</p>
    </div>
  )
}

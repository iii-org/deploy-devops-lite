import { useState } from 'react'

import { Button } from '../Button'
import { FormGroup } from './FormGroup'
import './modal.css'

export function Modal({ closeModal, createTask }) {
  const [description, setDescription] = useState('')

  const [date, setDate] = useState('')

  return (
    <div className="modal-background">
      <article className="modal-container">
        <h2 className="title-modal">Add New Task</h2>

        <form>
          <FormGroup
            type="text"
            id="description"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            label="Task Description"
          />

          <FormGroup type="date" id="date" value={date} onChange={(e) => setDate(e.target.value)} label="Start Date" />

          <div className="buttons-modal">
            <Button onClick={() => closeModal()} className="btn-cancel" title="Cancel" />

            <Button onClick={() => createTask(description, date)} className="btn-save" title="Save" />
          </div>
        </form>
      </article>
    </div>
  )
}

import { useState, useEffect } from 'react'

import { SaveTaskInLocalStorage, getTasks, deleteTaskInLocalStorage } from './Storage'

import { Header } from './Components/Header/index'
import { Footer } from './Components/Footer/index'
import { TaskCounter } from './Components/TaskCounter'
import { Button } from './Components/Button'
import { Table } from './Components/Table/index'
import { Modal } from './Components/Modal/index'
import { Alert } from './Components/Alert/index'
import './css/reset.css'
import './css/index.css'

function App() {
  const [tasks, setTasks] = useState([])
  const [taskCounter, setTaskCounter] = useState([])
  const [statusMessage, setStatusMessage] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [showAlert, setShowAlert] = useState(false)
  const [messageAlert, setMessageAlert] = useState('')

  function loadTasks() {
    const allTasks = getTasks()

    if (allTasks.length === 0) {
      setStatusMessage('No tasks at all.')
    } else {
      setStatusMessage('')
    }
    setTaskCounter(allTasks.length)
    setTasks(allTasks)
  }

  function createTask(description, date) {
    if (!description || !date) {
      setShowAlert(true)
      setMessageAlert('Para continuar, preencha todos os campos!')
      return
    }
    SaveTaskInLocalStorage(description, date, tasks)
    loadTasks()
    setShowModal(false)
    setMessageAlert('')
  }

  useEffect(() => {
    loadTasks()
  }, [])

  useEffect(() => {
    if (showAlert) {
      setTimeout(() => {
        setShowAlert(false)
      }, 5000)
    }
  }, [showAlert])

  function closeModal() {
    setShowModal(false)
  }

  function removeTask(id) {
    deleteTaskInLocalStorage(id, tasks)
    loadTasks()
  }

  return (
    <>
      <div className="container">
        <Header />

        <main className="content">
          <div className="main-header">
            {console.log(import.meta.env.VITE_REACT_APP_APPURL)}
            <Button onClick={() => setShowModal(true)} className="btn-new-task" title="+ New Task" />

            <TaskCounter tasks={taskCounter} />
          </div>

          <Table tasks={tasks} removeTask={removeTask} />

          <h3 className="message-status">{statusMessage}</h3>
        </main>

        <Footer />
      </div>

      {showModal && <Modal closeModal={closeModal} createTask={createTask} />}

      {showAlert && <Alert message={messageAlert} closeAlert={setShowAlert} />}
    </>
  )
}

export default App

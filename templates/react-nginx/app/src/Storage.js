export function SaveTaskInLocalStorage(description, date, tasks) {
  const newTask = {
    description: description,
    date: new Date(date).toLocaleDateString('pt-BR', { timeZone: 'UTC' }),
    id: Math.floor(Math.random() * 10000)
  }

  localStorage.setItem('@JustDoIt', JSON.stringify([...tasks, newTask]))
}

export function deleteTaskInLocalStorage(id, tasks) {
  const filteredTasks = tasks.filter((task) => task.id !== id)

  localStorage.setItem('@JustDoIt', JSON.stringify(filteredTasks))
}

export function getTasks() {
  return JSON.parse(localStorage.getItem('@JustDoIt')) || []
}

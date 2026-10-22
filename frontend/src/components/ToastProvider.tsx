/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, type ReactNode } from 'react'
import { CircleCheck, CircleX, X } from 'lucide-react'

type ToastKind = 'success' | 'error'
type ToastEntry = { id: number; kind: ToastKind; message: string }
type ToastContextValue = (kind: ToastKind, message: string) => void

const ToastContext = createContext<ToastContextValue>(() => undefined)
let nextToastId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([])

  function notify(kind: ToastKind, message: string) {
    const id = ++nextToastId
    setToasts((current) => [...current, { id, kind, message }])
    window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 4500)
  }

  function dismiss(id: number) {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-stack" aria-label="Notifications" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => {
          const Icon = toast.kind === 'success' ? CircleCheck : CircleX
          return <div className={`toast toast--${toast.kind}`} key={toast.id} role={toast.kind === 'error' ? 'alert' : 'status'}>
            <Icon size={18} aria-hidden="true" /><span>{toast.message}</span>
            <button className="icon-button" type="button" aria-label="Dismiss message" title="Dismiss message" onClick={() => dismiss(toast.id)}><X size={15} aria-hidden="true" /></button>
          </div>
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
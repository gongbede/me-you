import type { ReactNode } from 'react'

export function PageHeader({
  section,
  title,
  description,
  action,
}: {
  section: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <header className="page-heading-row page-header">
      <div>
        <span className="eyebrow">{section}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  )
}
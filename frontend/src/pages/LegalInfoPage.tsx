import { PageHeader } from '../components/PageHeader'

const pages = {
  privacy: {
    section: 'INFORMATION',
    title: 'Privacy',
    description: 'Privacy information for the Me&You community.',
    message: 'Our privacy information will be published here soon.',
  },
  terms: {
    section: 'INFORMATION',
    title: 'Terms',
    description: 'Terms for using the Me&You community.',
    message: 'Our terms of service will be published here soon.',
  },
  contact: {
    section: 'SUPPORT',
    title: 'Contact',
    description: 'Get help with your Me&You account.',
    message: 'Contact details will be published here soon.',
  },
} as const

export function LegalInfoPage({ kind }: { kind: keyof typeof pages }) {
  const page = pages[kind]
  return (
    <main className="page-shell page-stack">
      <PageHeader section={page.section} title={page.title} description={page.description} />
      <section className="card" aria-label={page.title}>
        <p>{page.message}</p>
      </section>
    </main>
  )
}
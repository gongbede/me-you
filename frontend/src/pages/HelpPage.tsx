import { CircleHelp } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'

const helpTopics = [
  ['How do I post?', 'Open Home, write an update, and choose Post. You can add up to four images with alt text.'],
  ['How do I upload a video?', 'Open Videos, choose Upload video, fill in the details, and publish a supported video file.'],
  ['How do I join a class?', 'Open My Courses, choose a course, then open Classrooms and select a live session.'],
  ['How do I report something?', 'Use the report control beside a post, comment, message, video, or reel and choose a reason.'],
  ['How do I install the app?', 'Use your browser’s install option when it is available. The app shell can also open offline.'],
] as const

export function HelpPage() {
  return (
    <main className="page-shell page-stack">
      <PageHeader section="SUPPORT" title="Help" description="Quick answers for getting around Me&You." />
      <section className="help-list" aria-label="Help topics">
        {helpTopics.map(([question, answer]) => <article className="help-item" key={question}>
          <CircleHelp size={19} aria-hidden="true" />
          <div><h2>{question}</h2><p>{answer}</p></div>
        </article>)}
      </section>
    </main>
  )
}
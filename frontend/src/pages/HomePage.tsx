import { ArrowRight, Compass, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function HomePage() {
  const { user } = useAuth()

  return (
    <div className="page-stack">
      <section className="welcome-block">
        <div>
          <span className="eyebrow">YOUR COMMUNITY</span>
          <h1>Good things grow <span>together.</span></h1>
          <p>Welcome in, {user?.username}. Make today a little more curious.</p>
        </div>
        <div className="welcome-stamp" aria-hidden="true"><Sparkles size={30} /><span>learn<br />with joy</span></div>
      </section>

      <section className="home-empty" aria-labelledby="home-empty-title">
        <div className="empty-illustration" aria-hidden="true">
          <span className="empty-orbit empty-orbit--a" />
          <span className="empty-orbit empty-orbit--b" />
          <span className="empty-center"><Compass size={34} strokeWidth={1.8} /></span>
          <span className="empty-dot empty-dot--teal" />
          <span className="empty-dot empty-dot--amber" />
        </div>
        <div className="home-empty__copy">
          <span className="eyebrow">A FRESH START</span>
          <h2 id="home-empty-title">Your next chapter is open.</h2>
          <p>Your learning space is ready. Add a little about yourself and make it yours.</p>
          <Link className="button button--primary" to="/profile">Set up your profile <ArrowRight size={17} /></Link>
        </div>
      </section>

      <section className="home-note" aria-label="Me&You tagline">
        <span className="home-note__dot" />
        <p><strong>Learn.</strong> <strong>Connect.</strong> <strong>Grow.</strong></p>
        <span className="home-note__caption">One step at a time.</span>
      </section>
    </div>
  )
}
import { useEffect, useState } from 'react'

const STEPS = {
  signin: ['Checking your account', 'Opening your workspace', 'Starting your private Python sandbox', 'Loading your data into it', 'Almost ready'],
  signup: ['Creating your account', 'Setting up your workspace', 'Starting your private Python sandbox', 'Loading your data into it', 'Almost ready'],
}

export default function Starting({ mode = 'signin', via = '' }) {
  const steps = STEPS[mode]
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 1800)
    return () => clearInterval(id)
  }, [steps.length])

  return (
    <div className="starting" role="status" aria-live="polite">
      <p className="starting-title">Starting your private sandbox</p>
      <p className="starting-sub">{via ? `Signed in with ${via}. ` : ''}Every workspace gets its own isolated Python machine, so your data never mixes with anyone else's.</p>
      <div className="starting-bar" aria-hidden="true"><span /></div>
      <ol className="starting-steps">
        {steps.map((s, i) => (
          <li key={s} className={i < step ? 'done' : i === step ? 'now' : ''}>
            <span className="starting-mark" aria-hidden="true">{i < step ? '✓' : i === step ? <span className="mini-spin" /> : ''}</span>{s}
          </li>
        ))}
      </ol>
      <p className="starting-note">This usually takes 10 to 20 seconds.</p>
    </div>
  )
}

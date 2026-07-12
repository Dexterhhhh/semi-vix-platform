import type { CalculationJob } from '../types'
export function JobProgress({ job }: { job: CalculationJob }) {
  return <div className="job"><div><strong>{job.type}</strong><span>{job.status}</span></div><div className="progress"><i style={{ width: `${job.progress}%` }} /></div><small>{job.start_date} → {job.end_date} · {job.progress}%</small></div>
}

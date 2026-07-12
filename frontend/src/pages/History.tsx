import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { createJob, getJobs } from '../api/jobs'
import { JobProgress } from '../components/JobProgress'

export function History() {
  const [start, setStart] = useState('2025-01-01'); const [end, setEnd] = useState(new Date().toISOString().slice(0, 10)); const client = useQueryClient()
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: getJobs, refetchInterval: 5000 })
  const create = useMutation({ mutationFn: createJob, onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }) })
  return <main><header><div><p className="eyebrow">HISTORICAL CALCULATION</p><h1>历史计算</h1></div></header><section className="panel form"><label>开始日期<input type="date" value={start} onChange={(event) => setStart(event.target.value)}/></label><label>结束日期<input type="date" value={end} onChange={(event) => setEnd(event.target.value)}/></label><button onClick={() => create.mutate({ start_date: start, end_date: end, frequency: 'daily' })} disabled={create.isPending}>创建计算任务</button>{create.isError && <p className="error">任务提交失败，请检查 Worker 与 Redis 状态。</p>}</section><section className="panel"><h3>最近任务</h3>{jobs.data?.map((job) => <JobProgress key={job.id} job={job}/>) ?? <p className="empty">暂无任务</p>}</section></main>
}

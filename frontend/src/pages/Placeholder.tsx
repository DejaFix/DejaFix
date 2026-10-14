import { Icon, type IconName } from '../components/Icon'

interface Props { title: string; icon: IconName; description: string }

export default function Placeholder({ title, icon, description }: Props) {
  return (
    <div className="page">
      <div className="page-head"><h1 className="page-title">{title}</h1></div>
      <div className="card empty">
        <div style={{ marginBottom: 12 }}><Icon name={icon} size={32} /></div>
        <h2>준비 중입니다</h2>
        <p>{description}</p>
      </div>
    </div>
  )
}

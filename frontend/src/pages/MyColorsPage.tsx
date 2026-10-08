// Menu użytkownika → Moje kolory: własne barwy motywów na wierzchu firmowych (Administracja → Kolory).
import { ColorsEditor } from './admin/colors/ColorsEditor'

export default function MyColorsPage() {
  return <div className="page"><ColorsEditor scope="personal" /></div>
}

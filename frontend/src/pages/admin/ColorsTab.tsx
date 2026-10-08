// Administracja → Kolory: kolory firmowe (dla wszystkich); edytor wspólny z „Moje kolory”.
import { ColorsEditor } from './colors/ColorsEditor'

export default function ColorsTab() {
  return <ColorsEditor scope="company" />
}

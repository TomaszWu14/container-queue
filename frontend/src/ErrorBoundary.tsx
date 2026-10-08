import { Component, ErrorInfo, ReactNode } from 'react'
import { sendClientError } from './clientError'

// Ostatnia linia obrony: wyjątek w renderze którejkolwiek strony NIE odmontowuje całej
// aplikacji (biały ekran), tylko pokazuje fallback z opcją odświeżenia. Boundary MUSI być
// klasą (hooki tu nie działają); komunikat wstrzykujemy propem, bo klasa nie ma useT.
// resetKey: zmiana (np. ścieżki) zdejmuje fallback — po błędzie jednej strony nawigacja
// na inną działa bez F5 (dawniej każda trasa pokazywała „Coś poszło nie tak”).
interface Props { children: ReactNode; fallback: ReactNode; resetKey?: unknown }
interface State { hasError: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
    // zgłoszenie na backend (/api/client-error) — z component stackiem zamiast JS stacku
    sendClientError(error.name, error.message,
      `${error.stack ?? ''}\n[componentStack]${info.componentStack ?? ''}`)
  }

  componentDidUpdate(prev: Props) {
    if (this.state.hasError && prev.resetKey !== this.props.resetKey) this.setState({ hasError: false })
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children
  }
}

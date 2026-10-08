export interface SeededUser {
  login: string
  companyId: number
}

export interface SeedData {
  /** wspólne hasło wszystkich zasianych userów E2E */
  password: string
  userA: SeededUser
  userB: SeededUser
  containerA: { no: string }
  containerB: { id: number; no: string }
}

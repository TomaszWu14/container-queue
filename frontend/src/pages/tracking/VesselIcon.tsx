/** Sylwetka kontenerowca top-down (dziób na -Y), ~18 jednostek długości.
    Wspólna dla mapy trackingu i mini-mapy karty kontenera — zamiast
    generycznego trójkąta/kółka. Obrót wg kursu robi rodzic (rotate). */
export default function VesselIcon() {
  return (
    <g>
      <path
        d="M0,-9 C2.6,-6.2 3.4,-4 3.4,-1.2 L3.4,6.2 Q3.4,7.6 2,7.6 L-2,7.6 Q-3.4,7.6 -3.4,6.2 L-3.4,-1.2 C-3.4,-4 -2.6,-6.2 0,-9 Z"
        fill="#f5a623" stroke="#10161f" strokeWidth="1" />
      {/* rzędy kontenerów na pokładzie */}
      <g fill="#10161f" opacity="0.5">
        <rect x="-2.1" y="-3.4" width="4.2" height="1.6" rx="0.3" />
        <rect x="-2.1" y="-1" width="4.2" height="1.6" rx="0.3" />
        <rect x="-2.1" y="1.4" width="4.2" height="1.6" rx="0.3" />
      </g>
      {/* mostek przy rufie */}
      <rect x="-2.3" y="4.2" width="4.6" height="2" rx="0.4"
            fill="#fff" opacity="0.9" stroke="#10161f" strokeWidth="0.5" />
    </g>
  )
}

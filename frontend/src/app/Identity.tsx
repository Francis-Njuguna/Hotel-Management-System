/** Original geometric mark and façade illustration. No external asset or font dependency. */
export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className="brand-lockup" aria-label="Hotel A, Front Office">
    <svg className="brand-mark" viewBox="0 0 44 44" fill="none" aria-hidden="true">
      <rect x=".7" y=".7" width="42.6" height="42.6" rx="12" fill="#3869D2" stroke="#8CAEF6" strokeWidth="1.4" />
      <path d="M9 33.5 19.8 10.6a2.45 2.45 0 0 1 4.4 0L35 33.5h-5.8L22 17.4l-7.3 16.1H9Z" fill="white" />
      <path d="M18.2 31v-2.1a3.8 3.8 0 0 1 7.6 0V31" stroke="#BCE0FF" strokeWidth="2.4" />
    </svg>
    {!compact && <div className="brand-type"><strong>Hotel A</strong><span>Front Office</span></div>}
  </div>;
}

export function HotelFacade({ className = '' }: { className?: string }) {
  return <svg className={`hotel-facade ${className}`} viewBox="0 0 390 190" fill="none" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">
    <g stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round">
      <path opacity=".42" d="M8 162h369M41 169h289M74 177h168M38 105V81h22m271 62V84h29v59m-8-58V70h-9v14" />
      <path d="M51 161V98h60v63m-64-63h68v-6H47v6Zm227 63V98h61v63m-65-63h69v-6h-69v6Z" />
      <path d="M103 161V65h63m-67 0h67v-6H99v6Zm180 96V65h-63m67 0h-67v-6h67v6Z" />
      <path d="M160 161V43l33-17 33 17v118M155 44l38-20 38 20-2 5-36-18-36 18-2-5Z" />
      <path d="M173 161v-30a20 20 0 0 1 40 0v30m-34 0v-28a14 14 0 0 1 28 0v28m-14-41v41m-30-1h60m-65 4h70" />
      <path d="M193 24V8m0 1c6-4 12 5 18 0v9c-7 4-12-4-18 0m-21 80h42m-42-5h42" />
      {[53, 71].map((y) => <g key={y}>{[174, 189, 204].map((x) => <path key={x} d={`M${x} ${y+12}v-8a4 4 0 0 1 8 0v8h-8Z`} />)}</g>)}
      {[77, 100, 124].map((y) => <g key={y}>{[113, 129, 145, 231, 247, 263].map((x) => <path key={x} d={`M${x} ${y}h7v13h-7zm-1 15h9`} />)}</g>)}
      {[109, 133].map((y) => <g key={y}>{[59, 76, 92, 285, 302, 319].map((x) => <path key={x} d={`M${x} ${y+11}v-7a4 4 0 0 1 8 0v7h-8Z`} />)}</g>)}
      <path d="M32 161v-25m-7 5c-4-7 0-21 7-32 8 12 12 25 7 32-3 5-11 5-14 0Zm331 20v-25m-7 5c-4-7 0-21 7-32 8 12 12 25 7 32-3 5-11 5-14 0Z" />
    </g>
  </svg>;
}

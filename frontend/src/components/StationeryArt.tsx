/** Original stationery illustrations, also used when a catalog photo is unavailable. */
export function StationeryArt({ variant = 'hero', className = '' }: { variant?: string; className?: string }) {
  const pen = /pen|ruchka|pencil|qalam|marker/i.test(variant);
  const paper = /a4|paper|qog|notebook|daftar/i.test(variant);
  const folder = /folder|papka|file/i.test(variant);
  return (
    <svg viewBox="0 0 440 350" fill="none" className={className} aria-hidden="true">
      <ellipse cx="224" cy="301" rx="173" ry="19" fill="#153F32" opacity=".08" />
      {(!pen || variant === 'hero') && <g transform="rotate(-12 188 185)">
        <rect x="99" y="62" width="179" height="237" rx="12" fill={folder ? '#EE7938' : '#153F32'} />
        <rect x="110" y="62" width="168" height="231" rx="9" fill={folder ? '#F29D64' : '#2C5C48'} />
        <path d="M130 62V294" stroke="#153F32" strokeWidth="3" opacity=".4" />
        <rect x="154" y="112" width="96" height="102" rx="3" fill="#F7F8F2" />
        <path d="M171 136H234M171 149H221M171 175H234M171 188H214" stroke="#153F32" strokeWidth="3" opacity=".35" />
        <text x="203" y="248" textAnchor="middle" fill="#E4EDE5" fontFamily="sans-serif" fontSize="13" letterSpacing="4">KANS</text>
        <path d="M93 89H112M93 114H112M93 139H112M93 164H112M93 189H112M93 214H112M93 239H112M93 264H112" stroke="#B9C7B5" strokeWidth="5" strokeLinecap="round" />
      </g>}
      {(paper || variant === 'hero') && <g transform="rotate(10 295 226)">
        <rect x="216" y="151" width="152" height="147" rx="4" fill="#DDE4D7" />
        <rect x="216" y="145" width="152" height="147" rx="4" fill="#FFFDF7" stroke="#D0D9C8" />
        <path d="M238 174H347M238 193H347M238 212H347M238 231H347M238 250H347M238 269H316" stroke="#DDE4D7" strokeWidth="2" />
        <path d="M248 145V292" stroke="#EE7938" opacity=".3" />
      </g>}
      {(pen || variant === 'hero') && <g transform={pen ? 'translate(80 -12) rotate(20 160 170)' : 'rotate(23 316 164)'}>
        <path d="M301 61H321V248L311 278L301 248V61Z" fill="#EE7938" />
        <path d="M307 61H315V248H307V61Z" fill="#F5B378" />
        <path d="M301 248L311 278L321 248" fill="#E5CC9E" />
        <path d="M307 266L311 278L315 266" fill="#23362C" />
        <rect x="300" y="44" width="22" height="25" rx="4" fill="#23362C" />
        {pen && <g transform="translate(-72 15)"><rect x="300" y="44" width="22" height="25" rx="4" fill="#B5C5AD"/><path d="M301 69H321V248L311 278L301 248V69Z" fill="#153F32"/><path d="M301 248L311 278L321 248" fill="#E5CC9E"/></g>}
      </g>}
      {variant === 'hero' && <>
        <g transform="rotate(-17 80 255)"><rect x="39" y="243" width="105" height="25" rx="3" fill="#ECC97D"/><path d="M50 244V257M65 244V251M80 244V257M95 244V251M110 244V257M125 244V251" stroke="#886D3F" strokeWidth="2"/></g>
        <g transform="rotate(16 341 89)"><path d="M330 54V102C330 119 352 119 352 102V63C352 49 337 49 337 63V99C337 107 345 107 345 99V70" stroke="#B5C5AD" strokeWidth="6" strokeLinecap="round"/></g>
        <path d="M58 96L61 105L70 108L61 111L58 120L55 111L46 108L55 105L58 96Z" fill="#EE7938"/>
        <circle cx="378" cy="226" r="5" fill="#EE7938"/><circle cx="344" cy="32" r="3" fill="#153F32" opacity=".3"/>
      </>}
    </svg>
  );
}

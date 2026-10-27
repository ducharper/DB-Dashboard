export default function ChromeLogo() {
  return <svg className="chrome-logo" viewBox="15 25 530 555" role="img" aria-label="Duc’s Backtester">
    <defs>
      <filter id="logo-clean-mask" colorInterpolationFilters="sRGB">
        <feComponentTransfer>
          <feFuncR type="linear" slope="1.1" intercept="-.08" />
          <feFuncG type="linear" slope="1.1" intercept="-.08" />
          <feFuncB type="linear" slope="1.1" intercept="-.08" />
        </feComponentTransfer>
      </filter>
      <mask id="logo-lettering" maskUnits="userSpaceOnUse" x="0" y="0" width="564" height="614" style={{ maskType: 'luminance' }}>
        <image href="/backtester-monogram.png" width="564" height="614" filter="url(#logo-clean-mask)" />
      </mask>
    </defs>
    <g mask="url(#logo-lettering)">
      <rect x="0" y="0" width="564" height="614" fill="#dedfd6" />
    </g>
  </svg>
}

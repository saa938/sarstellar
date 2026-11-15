export function FixtureTag({ className = "" }: { className?: string }) {
  return (
    <span className={`fixture-tag ${className}`} title="These dots and images are synthetic, generated to preview the design. Real NISAR bundles replace them as the science track ships them.">
      <i aria-hidden /> Synthetic preview data
    </span>
  );
}

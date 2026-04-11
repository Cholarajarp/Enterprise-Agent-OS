import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface KPICardProps {
  label: string;
  value: string;
  change?: { value: number; label: string };
  sparklineData?: number[];
  className?: string;
}

function Sparkline({ data, className }: { data: number[]; className?: string }) {
  if (data.length < 2) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const width = 80;
  const height = 24;

  const points = data.map((v, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - ((v - min) / range) * height,
  }));

  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
    .join(' ');

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn('w-20 h-6', className)}
      preserveAspectRatio="none"
    >
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-accent opacity-60"
      />
    </svg>
  );
}

export function KPICard({ label, value, change, sparklineData, className }: KPICardProps) {
  const isPositive = change && change.value > 0;
  const isNegative = change && change.value < 0;
  const isNeutral = !change || change.value === 0;

  return (
    <div className={cn('kpi-card', className)}>
      <p className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-2">
        {label}
      </p>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="font-display text-3xl font-bold text-txt-1 tabular-nums leading-none">
            {value}
          </p>
          {change && (
            <div className="flex items-center gap-1 mt-1.5">
              {isPositive && <TrendingUp size={11} className="text-success" />}
              {isNegative && <TrendingDown size={11} className="text-danger" />}
              {isNeutral && <Minus size={11} className="text-txt-3" />}
              <span
                className={cn(
                  'text-2xs font-medium',
                  isPositive && 'text-success',
                  isNegative && 'text-danger',
                  isNeutral && 'text-txt-3'
                )}
              >
                {isPositive && '+'}
                {change.value}% {change.label}
              </span>
            </div>
          )}
        </div>
        {sparklineData && <Sparkline data={sparklineData} />}
      </div>
    </div>
  );
}

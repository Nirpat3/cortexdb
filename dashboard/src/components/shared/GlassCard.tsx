'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

export function GlassCard({ children, className, hover, onClick }: GlassCardProps) {
  return (
    <motion.div
      className={cn(
        'glass rounded-2xl p-4',
        hover && 'cursor-pointer transition-colors hover:bg-[rgba(255,255,255,0.12)]',
        className
      )}
      whileHover={hover ? { scale: 1.02 } : undefined}
      whileTap={hover ? { scale: 0.98 } : undefined}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}

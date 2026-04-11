import type { Metadata } from 'next';
import { DM_Sans, JetBrains_Mono, Syne } from 'next/font/google';
import './globals.css';

const displayFont = Syne({
  subsets: ['latin'],
  variable: '--font-display',
  weight: ['400', '500', '600', '700'],
});

const bodyFont = DM_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700'],
});

const monoFont = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  weight: ['400', '500', '600', '700'],
});

export const metadata: Metadata = {
  title: 'Agent OS — Enterprise Agent Runtime',
  description: 'Production-grade governed multi-agent runtime platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`dark ${displayFont.variable} ${bodyFont.variable} ${monoFont.variable}`}
    >
      <body className="min-h-screen bg-void antialiased">
        {children}
      </body>
    </html>
  );
}

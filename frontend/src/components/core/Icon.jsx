import {
  Calculator,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Database,
  Download,
  Eye,
  EyeOff,
  Info,
  Landmark,
  Lock,
  LogOut,
  MessagesSquare,
  Mic,
  Pause,
  ScanFace,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  TriangleAlert,
  User,
  Volume2,
  X,
} from 'lucide-react';
import React from 'react';

const ICONS = {
  mic: Mic,
  square: Square,
  send: Send,
  'volume-2': Volume2,
  pause: Pause,
  user: User,
  landmark: Landmark,
  'log-out': LogOut,
  lock: Lock,
  'shield-check': ShieldCheck,
  'shield-alert': ShieldAlert,
  'scan-face': ScanFace,
  eye: Eye,
  'eye-off': EyeOff,
  check: Check,
  x: X,
  'circle-alert': CircleAlert,
  'circle-check': CircleCheck,
  'triangle-alert': TriangleAlert,
  info: Info,
  'chevron-down': ChevronDown,
  database: Database,
  calculator: Calculator,
  'messages-square': MessagesSquare,
  download: Download,
};

/** Monochrome Lucide glyph, inheriting the current text color. */
export function Icon({ name, size = 18, color = 'currentColor', strokeWidth = 2, style, ...rest }) {
  const Cmp = ICONS[name];
  const box = { display: 'inline-block', flex: 'none', width: size, height: size, ...style };
  if (!Cmp) return <span aria-hidden="true" {...rest} style={box} />;
  return (
    <Cmp
      aria-hidden="true"
      width={size}
      height={size}
      color={color}
      strokeWidth={strokeWidth}
      style={box}
      {...rest}
    />
  );
}

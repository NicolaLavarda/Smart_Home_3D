import {
  createElement,
  Globe,
  Video,
  Cctv,
  DoorOpen,
  Trees,
  Droplets,
  Sofa,
  Utensils,
  CookingPot,
  Flame,
  Compass,
  Settings,
  Moon,
  Sun,
  Tag,
  SlidersHorizontal,
  Rewind,
  Play,
  Pause,
  FastForward,
  Square,
  Power,
  Volume2,
  VolumeX,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Save,
  Crosshair,
  Brain,
  Footprints,
  User,
  Car,
  Truck,
  Bike,
  Dog,
  History,
  X,
  Zap,
  RefreshCw,
  Check,
  Home,
  Eye,
  EyeOff,
  LogIn,
  LogOut,
  Shield,
  ShieldCheck,
  UserCheck,
  Lock,
  AlertCircle,
} from 'lucide';

const ICON_MAP = {
  globe: Globe,
  video: Video,
  cctv: Cctv,
  'door-open': DoorOpen,
  trees: Trees,
  droplets: Droplets,
  sofa: Sofa,
  utensils: Utensils,
  'cooking-pot': CookingPot,
  flame: Flame,
  compass: Compass,
  settings: Settings,
  moon: Moon,
  sun: Sun,
  tag: Tag,
  'sliders-horizontal': SlidersHorizontal,
  rewind: Rewind,
  play: Play,
  pause: Pause,
  'fast-forward': FastForward,
  square: Square,
  power: Power,
  'volume-2': Volume2,
  'volume-x': VolumeX,
  'chevron-up': ChevronUp,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'rotate-ccw': RotateCcw,
  save: Save,
  crosshair: Crosshair,
  brain: Brain,
  footprints: Footprints,
  user: User,
  car: Car,
  truck: Truck,
  bike: Bike,
  dog: Dog,
  history: History,
  x: X,
  zap: Zap,
  'refresh-cw': RefreshCw,
  check: Check,
  home: Home,
  eye: Eye,
  'eye-off': EyeOff,
  'log-in': LogIn,
  'log-out': LogOut,
  shield: Shield,
  'shield-check': ShieldCheck,
  'user-check': UserCheck,
  lock: Lock,
  'alert-circle': AlertCircle,
};

/**
 * Generates an inline SVG string for a registered Lucide icon.
 * @param {string} name - Kebab-case icon name in ICON_MAP.
 * @param {Object} [options]
 * @param {number} [options.size=16]
 * @param {number} [options.strokeWidth=2]
 * @param {string} [options.className='']
 * @param {string} [options.fill='none']
 * @returns {string}
 */
export function icon(name, { size = 16, strokeWidth = 2, className = '', fill = 'none' } = {}) {
  const iconNode = ICON_MAP[name];
  if (!iconNode) {
    console.warn(`[icons] Icona non trovata: '${name}'`);
    return '';
  }

  const classes = className ? `lucide-icon ${className}` : 'lucide-icon';
  const el = createElement(iconNode, {
    width: size,
    height: size,
    'stroke-width': strokeWidth,
    fill,
    class: classes,
    'aria-hidden': 'true',
  });

  return el ? el.outerHTML : '';
}

import { useState, useEffect, useRef, useCallback, useMemo, type ReactNode, type MouseEvent } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";

// Icons
const FolderIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
);

const PlusIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

const SearchIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const MicIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
  </svg>
);

const ImageIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
    <circle cx="8.5" cy="8.5" r="1.5" />
    <polyline points="21 15 16 10 5 21" />
  </svg>
);

const BoxIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
  </svg>
);

const FilmIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
    <line x1="7" y1="2" x2="7" y2="22" />
    <line x1="17" y1="2" x2="17" y2="22" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <line x1="2" y1="7" x2="7" y2="7" />
    <line x1="2" y1="17" x2="7" y2="17" />
    <line x1="17" y1="17" x2="22" y2="17" />
    <line x1="17" y1="7" x2="22" y2="7" />
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

const LoaderIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="2" x2="12" y2="6" />
    <line x1="12" y1="18" x2="12" y2="22" />
    <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
    <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
  </svg>
);

const ActivityIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ChevronDownIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

const AlertCircleIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const RetryIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="1 4 1 10 7 10" />
    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
  </svg>
);

const EditIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const TrashIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

const GridSmallIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </svg>
);

const GridLargeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <rect x="3" y="3" width="18" height="8" rx="2" />
    <rect x="3" y="13" width="18" height="8" rx="2" />
  </svg>
);

const ListIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
    <line x1="6" y1="6" x2="21" y2="6" />
    <line x1="6" y1="12" x2="21" y2="12" />
    <line x1="6" y1="18" x2="21" y2="18" />
    <circle cx="3" cy="6" r="1" fill="currentColor" stroke="none" />
    <circle cx="3" cy="12" r="1" fill="currentColor" stroke="none" />
    <circle cx="3" cy="18" r="1" fill="currentColor" stroke="none" />
  </svg>
);

const FileIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

const FolderOpenIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1" />
    <path d="M3 10h18a2 2 0 0 1 2 2l-2 7a2 2 0 0 1-2 1H5a2 2 0 0 1-2-2Z" />
  </svg>
);

const CopyIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

const TagIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10l-8.5 8.5a2 2 0 0 1-2.8 0L4 13.8a2 2 0 0 1 0-2.8L12.2 2H20v8Z" />
    <circle cx="16" cy="8" r="1.5" />
  </svg>
);

const StarIcon = ({ filled = false }: { filled?: boolean }) => (
  <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15 9 22 9 16.5 14 18.5 22 12 17.5 5.5 22 7.5 14 2 9 9 9 12 2" />
  </svg>
);

const PlayIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none" />
  </svg>
);

const ShieldIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2l7 4v6c0 5-3.5 9-7 10-3.5-1-7-5-7-10V6l7-4z" />
  </svg>
);

const UsersIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="3" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a3 3 0 0 1 0 5.74" />
  </svg>
);

const ShareIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M16 5l6 6-6 6" />
    <path d="M8 18H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
    <path d="M4 12h12" />
  </svg>
);

const InfoIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="12" cy="12" r="10" />
    <path d="M12 8v4" />
    <path d="M12 16h.01" />
  </svg>
);

const MoreIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="6" cy="12" r="1.5" />
    <circle cx="12" cy="12" r="1.5" />
    <circle cx="18" cy="12" r="1.5" />
  </svg>
);

const HeartIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
  </svg>
);

const CameraIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
    <circle cx="12" cy="13" r="4" />
  </svg>
);

const isTauri = typeof window !== "undefined" && "__TAURI__" in window;

interface Library {
  library_id: string;
  folder_path: string;
  name: string;
  video_count: number;
  indexed_count: number;
}

interface Video {
  video_id: string;
  library_id?: string;
  path?: string;
  filename: string;
  file_size?: number | null;
  created_at_ms?: number;
  duration_ms?: number;
  status: string;
  progress: number;
  thumbnail_path?: string;
  error_code?: string;
  error_message?: string;
}

interface IndexingSummary {
  total: number;
  indexed: number;
  queued: number;
  processing: number;
  failed: number;
}

interface MediaItem {
  media_id: string;
  library_id: string;
  path: string;
  filename: string;
  file_ext?: string | null;
  media_type: "video" | "photo";
  file_size: number;
  mtime_ms: number;
  fingerprint: string;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  creation_time?: string | null;
  camera_make?: string | null;
  camera_model?: string | null;
  gps_lat?: number | null;
  gps_lng?: number | null;
  status: string;
  progress: number;
  error_code?: string | null;
  error_message?: string | null;
  indexed_at_ms?: number | null;
  created_at_ms: number;
  thumbnail_path?: string | null;
}

interface VideoDetails {
  video_id: string;
  filename: string;
  path: string;
  duration_ms?: number;
}

type SearchMode = "all" | "transcript" | "visual" | "objects";

const ALL_LIBRARIES_ID = "__all__";

interface ScanProgressEvent {
  type?: string;
  library_id: string;
  files_found: number;
  files_new: number;
  files_changed: number;
  files_deleted: number;
}

interface JobProgressEvent {
  job_id: string;
  video_id: string;
  stage?: string;
  progress?: number;
  message?: string;
  type: string;
}

interface PersonMatch {
  person_id: string;
  name: string;
  face_count: number;
}

interface SearchResult {
  video_id: string;
  timestamp_ms: number;
  score: number;
  transcript_snippet?: string | null;
  thumbnail_path?: string | null;
  labels?: string[] | null;
  persons?: PersonMatch[] | null;
  match_type: "transcript" | "visual" | "both";
}

interface Person {
  person_id: string;
  name: string;
  face_count: number;
  thumbnail_face_id?: string;
}

interface FrameInfo {
  frame_index: number;
  timestamp_ms: number;
  thumbnail_path: string;
}

interface FramesResponse {
  frames: FrameInfo[];
  total: number;
}

interface SearchResponse {
  results: SearchResult[];
  total: number;
  query_time_ms?: number;
}

interface GroupedSearchResult {
  video_id: string;
  filename: string;
  moments: SearchResult[];
  best_score: number;
  best_thumbnail?: string | null;
}

interface MainViewProps {
  scanProgress?: Map<string, ScanProgressEvent>;
  jobProgress?: Map<string, JobProgressEvent>;
  faceRecognitionEnabled?: boolean;
}

interface HoverPreviewProps {
  videoId: string;
  className: string;
  baseThumbnail?: string | null;
  resolveAssetUrl: (path?: string | null) => string;
  overlay?: ReactNode;
  placeholder: ReactNode;
  limit?: number;
  onClick?: () => void;
}

const HoverPreview = ({
  videoId,
  className,
  baseThumbnail,
  resolveAssetUrl,
  overlay,
  placeholder,
  limit = 15,
  onClick,
}: HoverPreviewProps) => {
  const [frames, setFrames] = useState<string[]>([]);
  const [frameIndex, setFrameIndex] = useState(0);
  const [hovering, setHovering] = useState(false);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const intervalRef = useRef<number | null>(null);

  const fetchFrames = useCallback(async () => {
    if (loadState === "loading") return;
    setLoadState("loading");
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<FramesResponse>(
        `/videos/${videoId}/frames?limit=${limit}`
      );
      const rawPaths = data.frames.map((frame) => frame.thumbnail_path).filter(Boolean);
      setFrames(rawPaths);
      setLoadState("ready");
    } catch (err) {
      console.error("Failed to load preview frames:", err);
      setLoadState("error");
    }
  }, [limit, loadState, videoId]);

  useEffect(() => {
    if (!hovering || frames.length < 2) return;
    intervalRef.current = window.setInterval(() => {
      setFrameIndex((idx) => (idx + 1) % frames.length);
    }, 1000);
    return () => {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [frames.length, hovering]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, []);

  const handleMouseEnter = () => {
    setHovering(true);
    if (frames.length === 0 && loadState !== "loading") {
      fetchFrames();
    }
  };

  const handleMouseLeave = () => {
    setHovering(false);
    setFrameIndex(0);
  };

  const currentSrc = hovering && frames.length > 0
    ? resolveAssetUrl(frames[frameIndex])
    : resolveAssetUrl(baseThumbnail) || resolveAssetUrl(frames[0]) || "";

  return (
    <div
      className={className}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : -1}
    >
      {currentSrc ? <img src={currentSrc} alt="" /> : placeholder}
      {overlay}
    </div>
  );
};

export function MainView({ scanProgress, jobProgress, faceRecognitionEnabled = false }: MainViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("all");
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState<string | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [indexingSummary, setIndexingSummary] = useState<IndexingSummary | null>(null);
  const [viewGranularity, setViewGranularity] = useState<"years" | "months" | "all">("all");
  const [selectedMediaId, setSelectedMediaId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [mediaTypeFilter, setMediaTypeFilter] = useState<"all" | "photo" | "video">("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [locationOnly, setLocationOnly] = useState(false);
  const [viewMode, setViewMode] = useState<"grid-sm" | "grid-lg" | "list">("grid-lg");
  const [sortMode, setSortMode] = useState<"newest" | "oldest">("newest");
  const [showPrivacyPanel, setShowPrivacyPanel] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [activePhoto, setActivePhoto] = useState<MediaItem | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [mediaTags, setMediaTags] = useState<Record<string, string[]>>({});
  const [lastScanTimes, setLastScanTimes] = useState<Record<string, number>>({});
  const [libraryAction, setLibraryAction] = useState<{ id: string; action: "scan" | "rename" | "delete" } | null>(null);
  const [indexingStarting, setIndexingStarting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showStatusPanel, setShowStatusPanel] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [expandedVideos, setExpandedVideos] = useState<Set<string>>(new Set());
  const [activeVideo, setActiveVideo] = useState<(VideoDetails & { timestamp_ms: number }) | null>(null);
  const [playerLoading, setPlayerLoading] = useState(false);
  const [playerError, setPlayerError] = useState<string | null>(null);
  const [apiBaseUrl, setApiBaseUrl] = useState<string>("");
  const [retryingFailed, setRetryingFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  // Person filtering state
  const [persons, setPersons] = useState<Person[]>([]);
  const [selectedPersons, setSelectedPersons] = useState<string[]>([]);
  const [showPersonPicker, setShowPersonPicker] = useState(false);
  const personPickerRef = useRef<HTMLDivElement | null>(null);

  // Close person picker when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (personPickerRef.current && !personPickerRef.current.contains(e.target as Node)) {
        setShowPersonPicker(false);
      }
    };
    if (showPersonPicker) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showPersonPicker]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedFavorites = window.localStorage.getItem("gaze.favorites");
    if (storedFavorites) {
      try {
        setFavoriteIds(new Set<string>(JSON.parse(storedFavorites)));
      } catch {
        setFavoriteIds(new Set());
      }
    }
    const storedTags = window.localStorage.getItem("gaze.tags");
    if (storedTags) {
      try {
        setMediaTags(JSON.parse(storedTags));
      } catch {
        setMediaTags({});
      }
    }
    const storedScans = window.localStorage.getItem("gaze.lastScans");
    if (storedScans) {
      try {
        setLastScanTimes(JSON.parse(storedScans));
      } catch {
        setLastScanTimes({});
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("gaze.favorites", JSON.stringify(Array.from(favoriteIds)));
  }, [favoriteIds]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("gaze.tags", JSON.stringify(mediaTags));
  }, [mediaTags]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("gaze.lastScans", JSON.stringify(lastScanTimes));
  }, [lastScanTimes]);

  useEffect(() => {
    if (!scanProgress) return;
    setLastScanTimes((prev) => {
      let updated = false;
      const next = { ...prev };
      scanProgress.forEach((scan, libraryId) => {
        if (scan && (scan as { type?: string }).type === "scan_complete") {
          next[libraryId] = Date.now();
          updated = true;
        }
      });
      return updated ? next : prev;
    });
    }, [scanProgress]);

  useEffect(() => {
    if (!selectedMediaId) return;
    if (!mediaItems.some((item) => item.media_id === selectedMediaId)) {
      setSelectedMediaId(null);
    }
  }, [selectedMediaId, mediaItems]);

  useEffect(() => {
    if (!menuOpenId) return;
    if (typeof document === "undefined") return;
    const handleOutside = () => setMenuOpenId(null);
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [menuOpenId]);


  // Fetch libraries on mount
  useEffect(() => {
    fetchLibraries();
  }, []);

  // Fetch persons when face recognition is enabled
  useEffect(() => {
    if (!faceRecognitionEnabled) {
      setPersons([]);
      setSelectedPersons([]);
      return;
    }
    fetchPersons();
  }, [faceRecognitionEnabled]);

  const fetchPersons = async () => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ persons: Person[] }>("/faces/persons");
      setPersons(data.persons || []);
    } catch (err) {
      setPersons([]);
      if (err instanceof Error && err.message.includes("403")) {
        return;
      }
      console.error("Failed to fetch persons:", err);
    }
  };

  useEffect(() => {
    if (isTauri) return;
    let mounted = true;
    const loadBaseUrl = async () => {
      try {
        const { getApiBaseUrl } = await import("../lib/apiClient");
        const baseUrl = await getApiBaseUrl();
        if (mounted) {
          setApiBaseUrl(baseUrl);
        }
      } catch (err) {
        console.error("Failed to resolve API base URL:", err);
      }
    };
    loadBaseUrl();
    return () => {
      mounted = false;
    };
  }, []);

  // Fetch media + videos when library changes (only if not searching)
  useEffect(() => {
    if (selectedLibrary && !isSearching) {
      fetchVideos(selectedLibrary);
      fetchMedia(selectedLibrary);
    }
  }, [selectedLibrary, isSearching, mediaTypeFilter, dateFrom, dateTo, locationOnly]);

  useEffect(() => {
    if (!showStatusPanel) return;
    let intervalId: number | null = null;
    const refresh = () => {
      fetchIndexingSummary(selectedLibrary);
    };
    refresh();
    intervalId = window.setInterval(refresh, 2000);
    return () => {
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [showStatusPanel, selectedLibrary]);

  // Refresh libraries and videos when scan completes
  useEffect(() => {
    if (!scanProgress) return;

    scanProgress.forEach((scan) => {
      if ((scan as { type?: string }).type === "scan_complete") {
        fetchLibraries();
        if (
          selectedLibrary === scan.library_id ||
          selectedLibrary === ALL_LIBRARIES_ID
        ) {
          fetchVideos(selectedLibrary);
          fetchMedia(selectedLibrary);
        }
      }
    });
  }, [scanProgress, selectedLibrary]);

  // Update video progress from WebSocket job events
  useEffect(() => {
    if (!jobProgress) return;

    setVideos(prevVideos => {
      let updated = false;
      const newVideos = prevVideos.map(video => {
        const job = Array.from(jobProgress.values()).find(j => j.video_id === video.video_id);
        if (job) {
          updated = true;
          if (job.type === "job_complete") {
            return { ...video, status: "DONE", progress: 1 };
          } else if (job.type === "job_progress" && job.progress !== undefined) {
            return { ...video, progress: job.progress, status: job.stage || video.status };
          }
        }
        return video;
      });
      return updated ? newVideos : prevVideos;
    });
  }, [jobProgress]);

  const fetchLibraries = async () => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ libraries: Library[] }>("/libraries");
      const libs = data.libraries || [];
      let nextLibraries = libs;

      if (libs.length > 0) {
        const totals = libs.reduce(
          (acc, lib) => {
            acc.video_count += lib.video_count || 0;
            acc.indexed_count += lib.indexed_count || 0;
            return acc;
          },
          { video_count: 0, indexed_count: 0 }
        );

        const allLibraries: Library = {
          library_id: ALL_LIBRARIES_ID,
          folder_path: "",
          name: "All Libraries",
          video_count: totals.video_count,
          indexed_count: totals.indexed_count,
        };
        nextLibraries = [allLibraries, ...libs];
      }

      setLibraries(nextLibraries);

      if (!selectedLibrary && nextLibraries.length > 0) {
        setSelectedLibrary(nextLibraries[0].library_id);
      } else if (
        selectedLibrary &&
        !nextLibraries.some((lib) => lib.library_id === selectedLibrary)
      ) {
        setSelectedLibrary(nextLibraries[0]?.library_id ?? null);
      }
    } catch (err) {
      console.error("Failed to fetch libraries:", err);
    }
  };

  const fetchVideos = async (libraryId: string) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const endpoint =
        libraryId === ALL_LIBRARIES_ID
          ? "/videos"
          : `/videos?library_id=${encodeURIComponent(libraryId)}`;
      const data = await apiRequest<{ videos: Video[]; total: number }>(endpoint);
      setVideos(data.videos || []);
    } catch (err) {
      console.error("Failed to fetch videos:", err);
    }
  };

  const fetchIndexingSummary = async (libraryId: string | null) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const params = new URLSearchParams();
      if (libraryId && libraryId !== ALL_LIBRARIES_ID) {
        params.set("library_id", libraryId);
      }
      const endpoint = params.toString() ? `/stats/indexing?${params.toString()}` : "/stats/indexing";
      const data = await apiRequest<IndexingSummary>(endpoint);
      setIndexingSummary(data);
    } catch (err) {
      console.error("Failed to fetch indexing summary:", err);
    }
  };

  const fetchMedia = async (libraryId: string) => {
    setMediaLoading(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const params = new URLSearchParams();
      if (libraryId !== ALL_LIBRARIES_ID) {
        params.set("library_id", libraryId);
      }
      if (mediaTypeFilter !== "all") {
        params.set("media_type", mediaTypeFilter);
      }
      if (dateFrom) {
        params.set("date_from", dateFrom);
      }
      if (dateTo) {
        params.set("date_to", dateTo);
      }
      if (locationOnly) {
        params.set("location_only", "true");
      }
      const endpoint = params.toString() ? `/media?${params.toString()}` : "/media";
      const data = await apiRequest<{ media: MediaItem[]; total: number }>(endpoint);
      setMediaItems(data.media || []);
    } catch (err) {
      console.error("Failed to fetch media:", err);
    } finally {
      setMediaLoading(false);
    }
  };

  const handleAddLibrary = async () => {
    // For now, prompt for folder path
    const folderPath = prompt("Enter folder path:");
    if (!folderPath) return;

    try {
      const { apiRequest } = await import("../lib/apiClient");
      await apiRequest<Library>("/libraries", {
        method: "POST",
        body: JSON.stringify({ folder_path: folderPath }),
      });
      fetchLibraries();
    } catch (err) {
      console.error("Failed to add library:", err);
    }
  };

  const handleStartIndexing = async () => {
    setIndexingStarting(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ status: string; message: string }>(
        "/jobs/start?limit=10",
        { method: "POST" }
      );
      console.log("Indexing started:", data);
      // Refresh videos to show status updates
      if (selectedLibrary) {
        setTimeout(() => fetchVideos(selectedLibrary), 1000);
        setTimeout(() => fetchMedia(selectedLibrary), 1000);
      }
    } catch (err) {
      console.error("Failed to start indexing:", err);
    } finally {
      setIndexingStarting(false);
    }
  };

  const handleRetryVideo = async (videoId: string) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      // Reset video status to QUEUED
      await apiRequest<void>(`/videos/${videoId}/retry`, { method: "POST" });
      // Refresh videos list
      if (selectedLibrary) {
        fetchVideos(selectedLibrary);
        fetchMedia(selectedLibrary);
      }
    } catch (err) {
      console.error("Failed to retry video:", err);
    }
  };

  const handleRetryAllFailed = async () => {
    if (retryingFailed) return;
    setRetryingFailed(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ success: boolean; retried: number; started: number }>(
        "/videos/retry-failed/all",
        { method: "POST" }
      );
      console.log("Retry failed videos response:", data);
      const targetLibrary = selectedLibrary || ALL_LIBRARIES_ID;
      fetchVideos(targetLibrary);
      fetchMedia(targetLibrary);
      fetchIndexingSummary(selectedLibrary);
    } catch (err) {
      console.error("Failed to retry failed videos:", err);
    } finally {
      setRetryingFailed(false);
    }
  };

  const handleSyncLibrary = async () => {
    if (!selectedLibrary || selectedLibrary === ALL_LIBRARIES_ID) {
      // Sync all libraries
      setSyncing(true);
      try {
        const { apiRequest } = await import("../lib/apiClient");
        for (const lib of libraries) {
          if (lib.library_id !== ALL_LIBRARIES_ID) {
            await apiRequest<{ status: string }>(
              `/libraries/${lib.library_id}/scan`,
              { method: "POST" }
            );
          }
        }
      } catch (err) {
        console.error("Failed to sync libraries:", err);
      } finally {
        setSyncing(false);
      }
    } else {
      // Sync selected library
      setSyncing(true);
      try {
        const { apiRequest } = await import("../lib/apiClient");
        await apiRequest<{ status: string }>(
          `/libraries/${selectedLibrary}/scan`,
          { method: "POST" }
        );
      } catch (err) {
        console.error("Failed to sync library:", err);
      } finally {
        setSyncing(false);
      }
    }
  };

  const handleScanLibrary = async (libraryId: string) => {
    if (libraryId === ALL_LIBRARIES_ID) {
      handleSyncLibrary();
      return;
    }
    setLibraryAction({ id: libraryId, action: "scan" });
    try {
      const { apiRequest } = await import("../lib/apiClient");
      await apiRequest<{ status: string }>(`/libraries/${libraryId}/scan`, { method: "POST" });
    } catch (err) {
      console.error("Failed to scan library:", err);
    } finally {
      setLibraryAction(null);
    }
  };

  const handleRenameLibrary = async (library: Library) => {
    if (library.library_id === ALL_LIBRARIES_ID) return;
    const currentName = library.name || getLibraryName(library);
    const nextName = prompt("Rename library:", currentName);
    if (!nextName) return;
    const trimmed = nextName.trim();
    if (!trimmed || trimmed === currentName) return;

    setLibraryAction({ id: library.library_id, action: "rename" });
    try {
      const { apiRequest } = await import("../lib/apiClient");
      await apiRequest(`/libraries/${library.library_id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed }),
      });
      fetchLibraries();
    } catch (err) {
      console.error("Failed to rename library:", err);
    } finally {
      setLibraryAction(null);
    }
  };

  const handleRemoveLibrary = async (library: Library) => {
    if (library.library_id === ALL_LIBRARIES_ID) return;
    const confirmed = confirm(
      `Remove "${getLibraryName(library)}"? This removes it from SafeKeeps Vault and deletes indexed data.`
    );
    if (!confirmed) return;

    setLibraryAction({ id: library.library_id, action: "delete" });
    try {
      const { apiRequest } = await import("../lib/apiClient");
      await apiRequest(`/libraries/${library.library_id}?purge_artifacts=true`, {
        method: "DELETE",
      });
      fetchLibraries();
    } catch (err) {
      console.error("Failed to remove library:", err);
    } finally {
      setLibraryAction(null);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedQuery = searchQuery.trim();

    // Allow search with just person filter (no query) or with a query
    if (!trimmedQuery && selectedPersons.length === 0) {
      // Clear search if query is empty and no persons selected
      setSearchResults([]);
      setIsSearching(false);
      if (selectedLibrary) {
        fetchVideos(selectedLibrary);
        fetchMedia(selectedLibrary);
      }
      return;
    }

    setSearchLoading(true);
    setIsSearching(true);

    try {
      const labels =
        searchMode === "objects"
          ? trimmedQuery.split(",").map((label) => label.trim()).filter(Boolean)
          : undefined;

      if (searchMode === "objects" && (!labels || labels.length === 0)) {
        setSearchResults([]);
        setSearchLoading(false);
        return;
      }

      // Map frontend searchMode to backend mode
      const backendMode: "transcript" | "visual" | "both" =
        searchMode === "all"
          ? "both"
          : searchMode === "transcript"
            ? "transcript"
            : searchMode === "visual"
              ? "visual"
              : "both";

      const requestBody: {
        query: string;
        mode: "transcript" | "visual" | "both";
        labels?: string[];
        person_ids?: string[];
        library_id?: string;
        limit: number;
      } = {
        query: searchMode === "objects" ? "" : trimmedQuery,
        mode: backendMode,
        limit: 50,
      };

      if (selectedLibrary) {
        if (selectedLibrary !== ALL_LIBRARIES_ID) {
          requestBody.library_id = selectedLibrary;
        }
      }
      if (labels && labels.length > 0) {
        requestBody.labels = labels;
      }
      if (selectedPersons.length > 0) {
        requestBody.person_ids = selectedPersons;
      }

      // Use apiClient for authenticated requests
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<SearchResponse>("/search", {
        method: "POST",
        body: JSON.stringify(requestBody),
      });

      setSearchResults(data.results || []);
    } catch (err) {
      console.error("Failed to search:", err);
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return "--:--";
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  const formatPhotoDate = (creationTime?: string | null, fallbackMs?: number | null) => {
    if (creationTime) {
      const normalized = creationTime.replace(/^(\d{4}):(\d{2}):(\d{2})/, "$1-$2-$3");
      const parsed = new Date(normalized);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
      }
    }
    if (fallbackMs) {
      const parsed = new Date(fallbackMs);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
      }
    }
    return "Unknown date";
  };

  const formatFileSize = (bytes?: number | null) => {
    if (!bytes || bytes <= 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    const precision = size >= 100 || unitIndex === 0 ? 0 : size >= 10 ? 1 : 2;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
  };

  const formatRelativeTime = (timestampMs?: number) => {
    if (!timestampMs) return "Not scanned yet";
    const diff = Date.now() - timestampMs;
    if (diff < 60_000) return "Just now";
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const getMediaTimestamp = (item: MediaItem) => {
    if (item.creation_time) {
      const normalized = item.creation_time.replace(/^(\d{4}):(\d{2}):(\d{2})/, "$1-$2-$3");
      const parsed = new Date(normalized);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.getTime();
      }
    }
    if (item.mtime_ms) {
      return item.mtime_ms;
    }
    return item.created_at_ms;
  };

  const sortedMediaItems = useMemo(() => {
    if (!mediaItems.length) return mediaItems;
    const items = [...mediaItems];
    items.sort((a, b) => {
      const delta = getMediaTimestamp(a) - getMediaTimestamp(b);
      return sortMode === "oldest" ? delta : -delta;
    });
    return items;
  }, [mediaItems, sortMode]);

  const temporalLabel = useMemo(() => {
    if (!sortedMediaItems.length) return "Moments are being organized";
    const timestamps = sortedMediaItems
      .map((item) => getMediaTimestamp(item))
      .filter(Boolean)
      .slice(0, 8)
      .sort((a, b) => a - b);
    if (!timestamps.length) return "Moments are being organized";
    const earliest = new Date(timestamps[0]);
    const latest = new Date(timestamps[timestamps.length - 1]);
    const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "short" });
    const dayFormatter = new Intl.DateTimeFormat("en-US", { day: "numeric" });
    const yearFormatter = new Intl.DateTimeFormat("en-US", { year: "numeric" });
    if (earliest.getFullYear() === latest.getFullYear()) {
      if (earliest.getMonth() === latest.getMonth()) {
        if (earliest.getDate() === latest.getDate()) {
          return `${monthFormatter.format(earliest)} ${dayFormatter.format(earliest)}, ${yearFormatter.format(latest)}`;
        }
        return `${monthFormatter.format(earliest)} ${dayFormatter.format(earliest)}–${dayFormatter.format(latest)}, ${yearFormatter.format(latest)}`;
      }
      return `${monthFormatter.format(earliest)} ${dayFormatter.format(earliest)} – ${monthFormatter.format(latest)} ${dayFormatter.format(latest)}, ${yearFormatter.format(latest)}`;
    }
    return `${monthFormatter.format(earliest)} ${dayFormatter.format(earliest)}, ${yearFormatter.format(earliest)} – ${monthFormatter.format(latest)} ${dayFormatter.format(latest)}, ${yearFormatter.format(latest)}`;
  }, [sortedMediaItems]);

  const getMediaPath = useCallback(
    (mediaId: string) => {
      const media = mediaItems.find((item) => item.media_id === mediaId);
      if (media?.path) return media.path;
      const video = videos.find((item) => item.video_id === mediaId);
      return video?.path ?? null;
    },
    [mediaItems, videos]
  );

  const resolveMediaPath = useCallback(
    async (mediaId: string) => {
      const cached = getMediaPath(mediaId);
      if (cached) return cached;
      try {
        const { apiRequest } = await import("../lib/apiClient");
        const data = await apiRequest<VideoDetails>(`/videos/${mediaId}`);
        return data.path ?? null;
      } catch (err) {
        console.warn("Unable to resolve media path:", err);
        return null;
      }
    },
    [getMediaPath]
  );

  const getFolderPath = (path?: string | null) => {
    if (!path) return null;
    const idx = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    if (idx === -1) return null;
    return path.slice(0, idx);
  };

  const handleOpenItem = async (mediaId: string, openFolder: boolean) => {
    if (!isTauri) return;
    const path = await resolveMediaPath(mediaId);
    const target = openFolder ? getFolderPath(path) : path;
    if (!target) {
      console.warn("No path available to open");
      return;
    }
    try {
      const { open } = await import("@tauri-apps/plugin-shell");
      await open(target);
    } catch (err) {
      console.error("Failed to open path:", err);
    }
  };

  const handleCopyItemPath = async (mediaId: string) => {
    const path = await resolveMediaPath(mediaId);
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
    } catch (err) {
      console.error("Failed to copy path:", err);
    }
  };

  const handleAddTag = (mediaId: string) => {
    const tag = prompt("Add a tag:");
    if (!tag) return;
    const normalized = tag.trim();
    if (!normalized) return;
    setMediaTags((prev) => {
      const next = { ...prev };
      const existing = new Set(next[mediaId] || []);
      existing.add(normalized);
      next[mediaId] = Array.from(existing);
      return next;
    });
  };

  const toggleFavorite = (mediaId: string) => {
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (next.has(mediaId)) {
        next.delete(mediaId);
      } else {
        next.add(mediaId);
      }
      return next;
    });
  };

  const handleShareAction = () => {
    if (!selectedMediaId) return;
    console.info("Share action triggered for", selectedMediaId);
  };

  const handleFavoriteAction = () => {
    if (!selectedMediaId) return;
    toggleFavorite(selectedMediaId);
  };

  const handleInfoAction = () => {
    if (!selectedMediaId) return;
    const media = mediaItems.find((item) => item.media_id === selectedMediaId);
    if (media) {
      setActivePhoto(media);
    }
  };

  const handleToolbarSearch = () => {
    searchInputRef.current?.focus();
  };

  const filtersActive =
    mediaTypeFilter !== "all" || locationOnly || Boolean(dateFrom) || Boolean(dateTo);
  const hasActiveFilters =
    searchMode !== "all" ||
    mediaTypeFilter !== "all" ||
    locationOnly ||
    Boolean(dateFrom) ||
    Boolean(dateTo) ||
    selectedPersons.length > 0;

  const clearAllFilters = () => {
    setSearchMode("all");
    setMediaTypeFilter("all");
    setLocationOnly(false);
    setDateFrom("");
    setDateTo("");
    setSelectedPersons([]);
  };

  const showHero = libraries.length === 0 && mediaItems.length === 0 && !isSearching;
  const activeLibrary = selectedLibrary
    ? libraries.find((lib) => lib.library_id === selectedLibrary) ?? null
    : null;
  const totalIndexed = activeLibrary
    ? activeLibrary.indexed_count
    : libraries.reduce((sum, lib) => sum + lib.indexed_count, 0);
  const totalItems = activeLibrary
    ? activeLibrary.video_count
    : libraries.reduce((sum, lib) => sum + lib.video_count, 0);
  const indexedCount = indexingSummary?.indexed ?? videos.filter(v => v.status === "DONE").length;
  const queuedCount = indexingSummary?.queued ?? videos.filter(v => v.status === "QUEUED").length;
  const processingCount = indexingSummary?.processing
    ?? videos.filter(v => !["DONE", "QUEUED", "FAILED", "CANCELLED"].includes(v.status)).length;
  const failedCount = indexingSummary?.failed ?? videos.filter(v => v.status === "FAILED").length;
  const queuedItems = videos.filter(v => v.status === "QUEUED").slice(0, 10);
  const failedItems = videos.filter(v => v.status === "FAILED").slice(0, 10);
  const activeScan = activeLibrary ? getLibraryScan(activeLibrary.library_id) : null;
  const isActiveScanning = activeScan && (activeScan as { type?: string }).type !== "scan_complete";
  const contextLibraryName =
    activeLibrary ? getLibraryName(activeLibrary) : libraries.length > 0 ? "All libraries" : "Library";
  const contextStatus = isActiveScanning
    ? `Scanning... ${activeScan?.files_found || 0} files found`
    : totalItems > 0
      ? `Indexed ${totalIndexed}/${totalItems}`
      : "Ready to scan";

  const getMatchLabel = (result: SearchResult) => {
    if (result.match_type === "both") return "Matched in transcript & visual";
    if (result.match_type === "transcript") return "Matched in transcript";
    if (result.match_type === "visual") return "Matched visually";
    return "Matched";
  };

  const formatTimestamp = (ms: number) => {
    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    }
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  function getLibraryName(lib: Library) {
    return lib.name || lib.folder_path.split(/[/\\]/).pop() || "Library";
  }

  function getLibraryScan(libraryId: string) {
    if (!scanProgress) return null;
    return scanProgress.get(libraryId);
  }

  const resolveAssetUrl = useCallback(
    (path?: string | null) => {
      if (!path) return "";
      if (isTauri) {
        return convertFileSrc(path);
      }
      if (!apiBaseUrl) {
        return "";
      }
      return `${apiBaseUrl}/assets/thumbnail?path=${encodeURIComponent(path)}`;
    },
    [apiBaseUrl]
  );

  const resolveMediaUrl = useCallback(
    (path?: string | null) => {
      if (!path) return "";
      if (isTauri) {
        return convertFileSrc(path);
      }
      if (!apiBaseUrl) {
        return "";
      }
      return `${apiBaseUrl}/assets/media?path=${encodeURIComponent(path)}`;
    },
    [apiBaseUrl]
  );

  const resolveVideoUrl = useCallback(
    (path?: string | null) => {
      if (!path) return "";
      if (isTauri) {
        const url = convertFileSrc(path);
        console.log("[Video] Tauri URL:", url);
        return url;
      }
      if (!apiBaseUrl) {
        console.warn("[Video] No API base URL available");
        return "";
      }
      const url = `${apiBaseUrl}/assets/video?path=${encodeURIComponent(path)}`;
      console.log("[Video] Web URL:", url);
      return url;
    },
    [apiBaseUrl]
  );

  const openPlayer = async (videoId: string, timestampMs: number = 0) => {
    setPlayerLoading(true);
    setPlayerError(null);
    setActiveVideo(null);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<VideoDetails>(`/videos/${videoId}`);
      // Start 3 seconds before the timestamp for context (but not before 0)
      const adjustedTimestamp = Math.max(0, timestampMs - 3000);
      setActiveVideo({ ...data, timestamp_ms: adjustedTimestamp });
    } catch (err) {
      console.error("Failed to load video details:", err);
      setPlayerError(err instanceof Error ? err.message : String(err));
    } finally {
      setPlayerLoading(false);
    }
  };

  // Group search results by video
  const groupedSearchResults = useMemo((): GroupedSearchResult[] => {
    if (!searchResults.length) return [];

    const groups = new Map<string, GroupedSearchResult>();

    for (const result of searchResults) {
      const existing = groups.get(result.video_id);
      const video = videos.find((v) => v.video_id === result.video_id);

      if (existing) {
        existing.moments.push(result);
        if (result.score > existing.best_score) {
          existing.best_score = result.score;
          existing.best_thumbnail = result.thumbnail_path;
        }
      } else {
        groups.set(result.video_id, {
          video_id: result.video_id,
          filename: video?.filename || result.video_id,
          moments: [result],
          best_score: result.score,
          best_thumbnail: result.thumbnail_path,
        });
      }
    }

    // Sort groups by best score descending
    return Array.from(groups.values()).sort((a, b) => b.best_score - a.best_score);
  }, [searchResults, videos]);

  const toggleVideoExpanded = (videoId: string) => {
    setExpandedVideos((prev) => {
      const next = new Set(prev);
      if (next.has(videoId)) {
        next.delete(videoId);
      } else {
        next.add(videoId);
      }
      return next;
    });
  };

  const closePlayer = () => {
    setActiveVideo(null);
    setPlayerError(null);
    setPlayerLoading(false);
  };

  useEffect(() => {
    if (!activeVideo || !videoRef.current) return;
    if (videoRef.current.readyState >= 1) {
      videoRef.current.currentTime = activeVideo.timestamp_ms / 1000;
    }
  }, [activeVideo]);

  const handlePlayerLoaded = () => {
    if (!activeVideo || !videoRef.current) return;
    videoRef.current.currentTime = activeVideo.timestamp_ms / 1000;
  };

  return (
    <div className="main-view">
      {/* Sidebar - Apple Gallery Style */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-title">Library</div>
        </div>

        {/* Global indexing progress bar */}
        {totalItems > 0 && totalIndexed < totalItems && (
          <div className="sidebar-progress-global">
            <div
              className="sidebar-progress-global-fill"
              style={{ width: `${Math.round((totalIndexed / totalItems) * 100)}%` }}
            />
          </div>
        )}

        <div className="sidebar-content">
          <div className="library-list">
            {libraries.map((lib) => {
              const scan = getLibraryScan(lib.library_id);
              const isScanning = scan && (scan as { type?: string }).type !== "scan_complete";
              const busyAction = libraryAction && libraryAction.id === lib.library_id;

              return (
                <div
                  key={lib.library_id}
                  className={`library-item ${selectedLibrary === lib.library_id ? "active" : ""} ${isScanning ? "scanning" : ""}`}
                  onClick={() => setSelectedLibrary(lib.library_id)}
                >
                  <div className="library-icon">
                    {isScanning ? <div className="spinner" style={{ width: 14, height: 14 }} /> : <FolderIcon />}
                  </div>
                  <div className="library-info">
                    <div className="library-name">{getLibraryName(lib)}</div>
                    <div className="library-badge">{lib.video_count}</div>
                  </div>
                  {lib.library_id !== ALL_LIBRARIES_ID && (
                    <div className="library-actions">
                      <button
                        className="btn-icon"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleScanLibrary(lib.library_id);
                        }}
                        disabled={busyAction}
                        title="Rescan"
                        type="button"
                      >
                        <RefreshIcon />
                      </button>
                      <button
                        className="btn-icon danger"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveLibrary(lib);
                        }}
                        disabled={busyAction}
                        title="Remove"
                        type="button"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}

            {libraries.length === 0 && (
              <div className="empty-state" style={{ padding: "32px 16px" }}>
                <div className="empty-state-icon" style={{ width: 48, height: 48, marginBottom: 12 }}>
                  <FolderIcon />
                </div>
                <h3 style={{ fontSize: 13 }}>No libraries</h3>
                <p style={{ fontSize: 11 }}>Add a folder to start</p>
              </div>
            )}
          </div>
        </div>

        <div className="sidebar-footer">
          <button className="btn add-library-btn" onClick={handleAddLibrary}>
            <PlusIcon />
            Add Folder
          </button>
        </div>
      </aside>

      {/* Content Area */}
      <div className="content-area">
        {/* Gallery Header - Compact */}
        <div className="search-section">
          <div className="progressive-header">
            <div className="hierarchy-row">
              {/* Gallery title */}
              <h1 className="gallery-title">
                {activeLibrary ? getLibraryName(activeLibrary) : "All Photos"}
              </h1>
              {/* View controls */}
              <div className="hierarchy-controls">
                {[
                  { id: "years", label: "Years" },
                  { id: "months", label: "Months" },
                  { id: "all", label: "All" },
                ].map((level) => (
                  <button
                    key={level.id}
                    type="button"
                    className={`hierarchy-pill ${viewGranularity === level.id ? "active" : ""}`}
                    onClick={() => setViewGranularity(level.id as "years" | "months" | "all")}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="context-toolbar">
              {/* Compact search */}
              <form onSubmit={handleSearch} className="search-container">
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  ref={searchInputRef}
                  onFocus={() => setShowFilters(true)}
                />
                <SearchIcon className="search-icon" />
              </form>

              {/* Filter toggle */}
              <button
                className={`filter-toggle ${showFilters || hasActiveFilters ? "active" : ""}`}
                onClick={() => setShowFilters(!showFilters)}
                type="button"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />
                </svg>
                Filter
                {hasActiveFilters && (
                  <span className="filter-count">
                    {(searchMode !== "all" ? 1 : 0) +
                      (mediaTypeFilter !== "all" ? 1 : 0) +
                      (locationOnly ? 1 : 0) +
                      (dateFrom ? 1 : 0) +
                      (dateTo ? 1 : 0) +
                      selectedPersons.length}
                  </span>
                )}
              </button>

              {/* Status indicator */}
              <button
                className="toolbar-status"
                onClick={() => setShowStatusPanel(true)}
                type="button"
              >
                <span className={`toolbar-status-dot ${processingCount > 0 ? "indexing" : ""}`} />
                {totalIndexed}/{totalItems}
              </button>
            </div>
          </div>

          {/* Collapsible Filters */}
          <div className={`facet-bar ${showFilters ? "visible" : ""}`}>
            <div className="facet-group">
              <div className="facet-label">Search in</div>
              <div className="facet-chips">
                <button
                  className={`chip ${searchMode === "all" ? "active" : ""}`}
                  onClick={() => setSearchMode("all")}
                  type="button"
                >
                  Everything
                </button>
                <button
                  className={`chip ${searchMode === "transcript" ? "active" : ""}`}
                  onClick={() => setSearchMode("transcript")}
                  type="button"
                >
                  <MicIcon />
                  Transcript
                </button>
                <button
                  className={`chip ${searchMode === "visual" ? "active" : ""}`}
                  onClick={() => setSearchMode("visual")}
                  type="button"
                >
                  <ImageIcon />
                  Visual
                </button>
                <button
                  className={`chip ${searchMode === "objects" ? "active" : ""}`}
                  onClick={() => setSearchMode("objects")}
                  type="button"
                >
                  <BoxIcon />
                  Objects
                </button>

                {/* Person filter */}
                {faceRecognitionEnabled && persons.length > 0 && (
                  <div className="person-filter-container" ref={personPickerRef}>
                    <button
                      className={`chip ${selectedPersons.length > 0 ? "active" : ""}`}
                      onClick={() => setShowPersonPicker(!showPersonPicker)}
                      type="button"
                    >
                      <UsersIcon />
                      Faces {selectedPersons.length > 0 && `(${selectedPersons.length})`}
                    </button>
                    {showPersonPicker && (
                      <div className="person-picker-dropdown">
                        <div className="person-picker-header">
                          <span>Filter by person</span>
                          {selectedPersons.length > 0 && (
                            <button
                              className="btn-link"
                              onClick={() => setSelectedPersons([])}
                              type="button"
                            >
                              Clear all
                            </button>
                          )}
                        </div>
                        <div className="person-picker-list">
                          {persons.map((person) => (
                            <label key={person.person_id} className="person-picker-item">
                              <input
                                type="checkbox"
                                checked={selectedPersons.includes(person.person_id)}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setSelectedPersons([...selectedPersons, person.person_id]);
                                  } else {
                                    setSelectedPersons(selectedPersons.filter(id => id !== person.person_id));
                                  }
                                }}
                              />
                              <span className="person-picker-name">{person.name}</span>
                              <span className="person-picker-count">{person.face_count}</span>
                            </label>
                          ))}
                        </div>
                        <div className="person-picker-footer">
                          <button
                            className="btn btn-small btn-primary"
                            onClick={() => {
                              setShowPersonPicker(false);
                              if (selectedPersons.length > 0 || searchQuery.trim()) {
                                handleSearch({ preventDefault: () => {} } as React.FormEvent);
                              }
                            }}
                            type="button"
                          >
                            Apply Filter
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="facet-group">
              <div className="facet-label">Media</div>
              <div className="facet-chips">
                <button
                  className={`chip ${mediaTypeFilter === "all" ? "active" : ""}`}
                  onClick={() => setMediaTypeFilter("all")}
                  type="button"
                >
                  All
                </button>
                <button
                  className={`chip ${mediaTypeFilter === "photo" ? "active" : ""}`}
                  onClick={() => setMediaTypeFilter("photo")}
                  type="button"
                >
                  <ImageIcon />
                  Photos
                </button>
                <button
                  className={`chip ${mediaTypeFilter === "video" ? "active" : ""}`}
                  onClick={() => setMediaTypeFilter("video")}
                  type="button"
                >
                  <FilmIcon />
                  Videos
                </button>
              </div>
            </div>

            <div className="facet-group facet-group-wide">
              <div className="facet-label">Date</div>
              <div className="facet-chips">
                <div className="date-filter">
                  <label>
                    From
                    <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                  </label>
                  <label>
                    To
                    <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                  </label>
                </div>
                <button
                  className={`chip ${locationOnly ? "active" : ""}`}
                  onClick={() => setLocationOnly(!locationOnly)}
                  type="button"
                >
                  Has location
                </button>
                {hasActiveFilters && (
                  <button
                    className="clear-filters"
                    onClick={clearAllFilters}
                    type="button"
                  >
                    Clear all
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Video Grid / Search Results */}
        <div className="video-grid-container">
          {!isSearching && mediaItems.length > 0 && (
            <div className="view-toolbar">
              <div className="view-toggle" role="group" aria-label="View mode">
                <button
                  className={`view-btn ${viewMode === "grid-sm" ? "active" : ""}`}
                  onClick={() => setViewMode("grid-sm")}
                  type="button"
                  aria-pressed={viewMode === "grid-sm"}
                  title="Small thumbnails"
                >
                  <GridSmallIcon />
                </button>
                <button
                  className={`view-btn ${viewMode === "grid-lg" ? "active" : ""}`}
                  onClick={() => setViewMode("grid-lg")}
                  type="button"
                  aria-pressed={viewMode === "grid-lg"}
                  title="Large thumbnails"
                >
                  <GridLargeIcon />
                </button>
                <button
                  className={`view-btn ${viewMode === "list" ? "active" : ""}`}
                  onClick={() => setViewMode("list")}
                  type="button"
                  aria-pressed={viewMode === "list"}
                  title="Detailed list"
                >
                  <ListIcon />
                </button>
              </div>
              <div className="sort-control">
                <span className="sort-label">Sort</span>
                <select
                  className="sort-select"
                  value={sortMode}
                  onChange={(e) => setSortMode(e.target.value as "newest" | "oldest")}
                  aria-label="Sort media"
                >
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                </select>
              </div>
            </div>
          )}
          {isSearching ? (
            searchLoading ? (
              <div className="empty-state">
                <div className="spinner spinner-large" />
                <p>Searching...</p>
              </div>
            ) : groupedSearchResults.length > 0 ? (
              <div className="search-results">
              <div className="results-header">
                <div className="results-count">
                  <strong>{searchResults.length}</strong> moments across <strong>{groupedSearchResults.length}</strong> items
                </div>
                {searchQuery && (
                  <div className="results-count">
                    for "{searchQuery}"
                  </div>
                  )}
                <div className="results-sort">
                  <span className="results-sort-label">Sort</span>
                  <span className="results-sort-pill">Relevance</span>
                </div>
                </div>
                {groupedSearchResults.map((group) => {
                  const isExpanded = expandedVideos.has(group.video_id);
                  const hasMultipleMoments = group.moments.length > 1;
                  const bestMoment = group.moments[0];
                  const matchLabel = getMatchLabel(bestMoment);
                  const isFavorite = favoriteIds.has(group.video_id);
                  const tags = mediaTags[group.video_id] || [];

                  return (
                    <div key={group.video_id} className="result-group">
                      {/* Main result card - shows best moment */}
                      <div
                        className="result-card result-card-main"
                        onClick={() => openPlayer(group.video_id, bestMoment.timestamp_ms)}
                      >
                        <HoverPreview
                          videoId={group.video_id}
                          className="result-thumbnail"
                          baseThumbnail={group.best_thumbnail ?? undefined}
                          resolveAssetUrl={resolveAssetUrl}
                          limit={15}
                          overlay={
                            <span className="result-timestamp">
                              {formatTimestamp(bestMoment.timestamp_ms)}
                            </span>
                          }
                          placeholder={
                            <div className="video-thumbnail-placeholder">
                              <FilmIcon />
                            </div>
                          }
                        />
                        <div className="result-content">
                          <div className="result-video-title">
                            {group.filename}
                          </div>
                          <div className="result-match">{matchLabel}</div>
                          {tags.length > 0 && (
                            <div className="result-user-tags">
                              {tags.map((tag) => (
                                <span key={tag} className="user-tag">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                          {bestMoment.transcript_snippet && (
                            <div
                              className="result-snippet"
                              dangerouslySetInnerHTML={{ __html: bestMoment.transcript_snippet }}
                            />
                          )}
                          <div className="result-tags">
                            {(bestMoment.match_type === "both" ? ["transcript", "visual"] : [bestMoment.match_type]).map((tag) => (
                              <span key={tag} className={`result-tag ${tag}`}>
                                {tag.charAt(0).toUpperCase() + tag.slice(1)}
                              </span>
                            ))}
                            {bestMoment.labels?.map((label) => (
                              <span key={label} className="result-tag object">
                                {label}
                              </span>
                            ))}
                            {bestMoment.persons?.map((person) => (
                              <span key={person.person_id} className="result-tag person">
                                <UsersIcon />
                                {person.name}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="result-actions">
                          <div className="result-primary-actions">
                            <button
                              className="btn-icon play-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                openPlayer(group.video_id, bestMoment.timestamp_ms);
                              }}
                              title="Play"
                            >
                              <PlayIcon />
                            </button>
                            {hasMultipleMoments && (
                              <button
                                className={`btn-icon expand-btn ${isExpanded ? "expanded" : ""}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleVideoExpanded(group.video_id);
                                }}
                                title={isExpanded ? "Collapse" : `Show all ${group.moments.length} moments`}
                              >
                                <span className="moment-count">{group.moments.length}</span>
                                <ChevronDownIcon />
                              </button>
                            )}
                          </div>
                          <div className="result-quick-actions">
                            <button
                              className="btn-icon subtle"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenItem(group.video_id, false);
                              }}
                              disabled={!isTauri}
                              title="Open file"
                              type="button"
                            >
                              <FileIcon />
                            </button>
                            <button
                              className="btn-icon subtle"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenItem(group.video_id, true);
                              }}
                              disabled={!isTauri}
                              title="Open folder"
                              type="button"
                            >
                              <FolderOpenIcon />
                            </button>
                            <button
                              className="btn-icon subtle"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCopyItemPath(group.video_id);
                              }}
                              title="Copy path"
                              type="button"
                            >
                              <CopyIcon />
                            </button>
                            <button
                              className="btn-icon subtle"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleAddTag(group.video_id);
                              }}
                              title="Add tag"
                              type="button"
                            >
                              <TagIcon />
                            </button>
                            <button
                              className={`btn-icon subtle ${isFavorite ? "active" : ""}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleFavorite(group.video_id);
                              }}
                              title={isFavorite ? "Remove favorite" : "Favorite"}
                              type="button"
                            >
                              <StarIcon filled={isFavorite} />
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Expanded moments list */}
                      {isExpanded && hasMultipleMoments && (
                        <div className="result-moments">
                          {group.moments.slice(1).map((moment, idx) => (
                            <div
                              key={`${moment.video_id}-${moment.timestamp_ms}-${idx}`}
                              className="result-moment"
                              onClick={() => openPlayer(moment.video_id, moment.timestamp_ms)}
                            >
                              <div className="moment-thumbnail">
                                {moment.thumbnail_path ? (
                                  <img
                                    src={resolveAssetUrl(moment.thumbnail_path)}
                                    alt=""
                                    loading="lazy"
                                  />
                                ) : (
                                  <div className="video-thumbnail-placeholder">
                                    <FilmIcon />
                                  </div>
                                )}
                              </div>
                              <div className="moment-info">
                                <span className="moment-timestamp">
                                  {formatTimestamp(moment.timestamp_ms)}
                                </span>
                                <span className="moment-match">{getMatchLabel(moment)}</span>
                                {moment.transcript_snippet && (
                                  <span
                                    className="moment-snippet"
                                    dangerouslySetInnerHTML={{ __html: moment.transcript_snippet }}
                                  />
                                )}
                              </div>
                              <button
                                className="btn-icon play-btn-small"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openPlayer(moment.video_id, moment.timestamp_ms);
                                }}
                                title="Play"
                              >
                                <PlayIcon />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <SearchIcon />
                </div>
                <h3>No results found</h3>
                <p>Try adjusting your search query or filters.</p>
              </div>
            )
          ) : mediaLoading ? (
            <div className="empty-state">
              <div className="spinner spinner-large" />
              <p>Loading your library...</p>
            </div>
          ) : mediaItems.length > 0 ? (
            <div className={`video-grid view-${viewMode}`}>
              {sortedMediaItems.map((item) => {
                const isVideo = item.media_type === "video";
                const video = isVideo ? videos.find((v) => v.video_id === item.media_id) : null;
                const status = video?.status ?? item.status;
                const progress = video?.progress ?? item.progress;
                const duration = video?.duration_ms ?? item.duration_ms ?? undefined;
                const isFavorite = favoriteIds.has(item.media_id);
                const isMenuOpen = menuOpenId === item.media_id;
                const toggleMenu = (event: MouseEvent<HTMLButtonElement>) => {
                  event.stopPropagation();
                  setMenuOpenId(isMenuOpen ? null : item.media_id);
                };
                const handleMenuAction =
                  (action: () => void) => (event: MouseEvent<HTMLButtonElement>) => {
                    event.stopPropagation();
                    action();
                    setMenuOpenId(null);
                  };

                const statusVariant = isVideo
                  ? status === "DONE"
                    ? "complete"
                    : status === "FAILED"
                      ? "failed"
                      : status === "QUEUED"
                        ? "queued"
                        : "processing"
                  : "photo";
                const statusLabel = isVideo
                  ? status === "DONE"
                    ? "Indexed"
                    : status === "FAILED"
                      ? "Failed"
                      : status === "QUEUED"
                        ? "Queued"
                        : "Indexing"
                  : "Photo";
                const statusIcon = isVideo
                  ? status === "DONE"
                    ? <CheckIcon />
                    : status === "FAILED"
                      ? <AlertCircleIcon />
                      : <LoaderIcon />
                  : <ImageIcon />;

                const overlayContent = (
                  <div className="media-overlay">
                    {/* Status dot - only for failed/indexing */}
                    {status === "FAILED" && <div className={`media-status-pill ${statusVariant}`} />}
                    {status !== "DONE" && status !== "FAILED" && status !== "QUEUED" && (
                      <div className="media-indexing-overlay">
                        <div className="spinner" />
                      </div>
                    )}
                    {status === "QUEUED" && <div className={`media-status-pill ${statusVariant}`} />}

                    {/* Video duration - bottom right */}
                    {isVideo && duration && (
                      <span className="video-duration">{formatDuration(duration)}</span>
                    )}

                    {/* Hover-to-reveal action menu */}
                    <div className="media-action">
                      <button
                        className="media-action-trigger"
                        type="button"
                        aria-haspopup="menu"
                        aria-expanded={isMenuOpen}
                        onClick={toggleMenu}
                      >
                        <MoreIcon />
                      </button>
                      {isMenuOpen && (
                        <div className="media-action-menu">
                          <button
                            type="button"
                            onClick={handleMenuAction(() => handleOpenItem(item.media_id, false))}
                          >
                            Open file
                          </button>
                          <button
                            type="button"
                            onClick={handleMenuAction(() => handleOpenItem(item.media_id, true))}
                          >
                            Open folder
                          </button>
                          <button
                            type="button"
                            onClick={handleMenuAction(() => handleCopyItemPath(item.media_id))}
                          >
                            Copy path
                          </button>
                          <button
                            type="button"
                            onClick={handleMenuAction(() => toggleFavorite(item.media_id))}
                          >
                            {isFavorite ? "Unfavorite" : "Favorite"}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );

                const handleCardClick = () => {
                  setMenuOpenId(null);
                  setSelectedMediaId(item.media_id);
                  if (isVideo) {
                    openPlayer(item.media_id, 0);
                  } else {
                    setActivePhoto(item);
                  }
                };

                return (
                  <div
                    key={item.media_id}
                    className={`video-card media-card ${isVideo ? "is-video" : "is-photo"} ${selectedMediaId === item.media_id ? "selected" : ""}`}
                    onClick={handleCardClick}
                  >
                    {isVideo ? (
                      <HoverPreview
                        videoId={item.media_id}
                        className="video-thumbnail"
                        baseThumbnail={item.thumbnail_path ?? undefined}
                        resolveAssetUrl={resolveAssetUrl}
                        limit={15}
                        overlay={overlayContent}
                        placeholder={
                          <div className="video-thumbnail-placeholder">
                            <FilmIcon />
                          </div>
                        }
                      />
                    ) : (
                      <div className="video-thumbnail photo-thumbnail">
                        {item.path ? (
                          <img src={resolveMediaUrl(item.path)} alt="" loading="lazy" />
                        ) : (
                          <div className="video-thumbnail-placeholder">
                            <ImageIcon />
                          </div>
                        )}
                        {overlayContent}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : filtersActive ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <ImageIcon />
              </div>
              <h3>No items match these filters</h3>
              <p>Try adjusting media type, date range, or location filters.</p>
            </div>
          ) : selectedLibrary ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <FilmIcon />
              </div>
              <h3>No photos or videos found</h3>
              <p>This library doesn't contain any photos or videos yet, or scanning is in progress.</p>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">
                <FolderIcon />
              </div>
              <h3>Select a library</h3>
              <p>Choose a library from the sidebar or add a new folder to get started.</p>
            </div>
          )}
        </div>

        {(activeVideo || playerLoading || playerError) && (
          <div className="player-overlay" onClick={closePlayer}>
            <div className="player-panel" onClick={(e) => e.stopPropagation()}>
              <div className="player-header">
                <div className="player-title">
                  {activeVideo?.filename ?? "Loading..."}
                </div>
                <button className="btn-icon" onClick={closePlayer} title="Close player">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
              <div className="player-body">
                {playerLoading ? (
                  <div className="player-loading">
                    <div className="spinner spinner-large" />
                    Loading video...
                  </div>
                ) : playerError ? (
                  <div className="player-error">{playerError}</div>
                ) : activeVideo ? (
                  <video
                    ref={videoRef}
                    className="player-video"
                    src={resolveVideoUrl(activeVideo.path)}
                    controls
                    autoPlay
                    onLoadedMetadata={handlePlayerLoaded}
                    onLoadedData={handlePlayerLoaded}
                    onError={(e) => {
                      const video = e.currentTarget;
                      const error = video.error;
                      console.error("Video error:", error?.code, error?.message);
                      setPlayerError(`Failed to load video: ${error?.message || "Unknown error"}`);
                    }}
                  />
                ) : null}
              </div>
              <div className="player-footer">
                <div className="player-meta">
                  Start {activeVideo ? formatTimestamp(activeVideo.timestamp_ms) : "--:--"}
                </div>
                <div className="player-meta">
                  Duration {activeVideo?.duration_ms ? formatDuration(activeVideo.duration_ms) : "--:--"}
                </div>
              </div>
            </div>
          </div>
        )}

        {activePhoto && (
          <div className="photo-overlay" onClick={() => setActivePhoto(null)}>
            <div className="photo-panel" onClick={(e) => e.stopPropagation()}>
              <div className="photo-header">
                <div className="photo-title">{activePhoto.filename}</div>
                <button className="btn-icon" onClick={() => setActivePhoto(null)} title="Close photo">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
              <div className="photo-body">
                <img src={resolveMediaUrl(activePhoto.path)} alt={activePhoto.filename} />
              </div>
              <div className="photo-footer">
                <div className="photo-meta">
                  {formatPhotoDate(activePhoto.creation_time, activePhoto.mtime_ms)}
                </div>
                <div className="photo-meta">
                  {activePhoto.width && activePhoto.height
                    ? `${activePhoto.width}×${activePhoto.height}`
                    : "Dimensions unknown"}
                </div>
                <div className="photo-meta">
                  {activePhoto.camera_make || activePhoto.camera_model
                    ? [activePhoto.camera_make, activePhoto.camera_model].filter(Boolean).join(" ")
                    : "Camera unknown"}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Status Panel */}
        {showStatusPanel && (
          <div className="player-overlay" onClick={() => setShowStatusPanel(false)}>
            <div className="status-panel" onClick={(e) => e.stopPropagation()}>
              <div className="status-panel-header">
                <div className="status-panel-title">
                  <ActivityIcon />
                  Indexing Status
                </div>
                <button className="btn-icon" onClick={() => setShowStatusPanel(false)} title="Close">
                  <CloseIcon />
                </button>
              </div>
              <div className="status-panel-body">
                {/* Summary Stats */}
                <div className="status-summary">
                  <div className="status-stat">
                    <div className="status-stat-value">{indexedCount}</div>
                    <div className="status-stat-label">Indexed</div>
                  </div>
                  <div className="status-stat">
                    <div className="status-stat-value">{queuedCount}</div>
                    <div className="status-stat-label">Queued</div>
                  </div>
                  <div className="status-stat">
                    <div className="status-stat-value">
                      {processingCount}
                    </div>
                    <div className="status-stat-label">Processing</div>
                  </div>
                  <div className="status-stat">
                    <div className="status-stat-value">{failedCount}</div>
                    <div className="status-stat-label">Failed</div>
                  </div>
                </div>

                {/* Active Jobs */}
                <div className="status-section">
                  <div className="status-section-title">Active Jobs</div>
                  {videos.filter(v => !["DONE", "QUEUED", "FAILED", "CANCELLED"].includes(v.status)).length === 0 ? (
                    <div className="status-empty">No active indexing jobs</div>
                  ) : (
                    <div className="status-job-list">
                      {videos
                        .filter(v => !["DONE", "QUEUED", "FAILED", "CANCELLED"].includes(v.status))
                        .map(video => {
                          const job = jobProgress ? Array.from(jobProgress.values()).find(j => j.video_id === video.video_id) : null;
                          return (
                            <div key={video.video_id} className="status-job-item">
                              <div className="status-job-info">
                                <div className="status-job-name">{video.filename}</div>
                                <div className="status-job-stage">
                                  {job?.stage || video.status}
                                  {job?.message && <span> - {job.message}</span>}
                                </div>
                              </div>
                              <div className="status-job-progress">
                                <div className="progress-bar" style={{ height: 6 }}>
                                  <div
                                    className="progress-fill"
                                    style={{ width: `${(job?.progress ?? video.progress) * 100}%` }}
                                  />
                                </div>
                                <div className="status-job-percent">
                                  {Math.round((job?.progress ?? video.progress) * 100)}%
                                </div>
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  )}
                </div>

                {/* Queued Videos */}
                <div className="status-section">
                  <div className="status-section-title">Queued Items ({queuedCount})</div>
                {queuedItems.length === 0 ? (
                    <div className="status-empty">No items in queue</div>
                ) : (
                    <div className="status-queue-list">
                      {queuedItems.map(video => (
                          <div key={video.video_id} className="status-queue-item">
                            <FilmIcon />
                            <span>{video.filename}</span>
                          </div>
                        ))}
                      {queuedCount > queuedItems.length && (
                        <div className="status-queue-more">
                          +{queuedCount - queuedItems.length} more
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Failed Videos */}
                {failedCount > 0 && (
                  <div className="status-section">
                    <div className="status-section-title status-failed">
                      <div className="status-failed-title">
                        <AlertCircleIcon />
                        Failed Items ({failedCount})
                      </div>
                      <button
                        className="retry-all-failed-btn"
                        type="button"
                        onClick={handleRetryAllFailed}
                        disabled={retryingFailed}
                        title="Retry all failed videos"
                      >
                        {retryingFailed ? <LoaderIcon /> : <RetryIcon />}
                        Retry all
                      </button>
                    </div>
                    <div className="status-failed-list">
                      {failedItems.map(video => (
                          <div key={video.video_id} className="status-failed-item">
                            <div className="status-failed-header">
                              <div className="status-failed-name">
                                <FilmIcon />
                                <span>{video.filename}</span>
                              </div>
                              <button
                                className="btn-icon retry-btn"
                                onClick={() => handleRetryVideo(video.video_id)}
                                title="Retry indexing"
                              >
                                <RetryIcon />
                              </button>
                            </div>
                            {video.error_message && (
                              <div className="status-failed-error">
                                <span className="error-code">{video.error_code || "ERROR"}</span>
                                <span className="error-message">{video.error_message}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      {failedCount > failedItems.length && (
                        <div className="status-queue-more">
                          +{failedCount - failedItems.length} more
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

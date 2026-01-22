import { useState, useEffect, useCallback, useMemo } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";

// Icons
const UserIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const UsersIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="3" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a3 3 0 0 1 0 5.74" />
  </svg>
);

const StarIcon = ({ filled = false }: { filled?: boolean }) => (
  <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15 9 22 9 16.5 14 18.5 22 12 17.5 5.5 22 7.5 14 2 9 9 9 12 2" />
  </svg>
);

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const PlusIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);


const GridIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);


const ClockIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const PlayIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none" />
  </svg>
);

const FilmIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
    <line x1="7" y1="2" x2="7" y2="22" />
    <line x1="17" y1="2" x2="17" y2="22" />
    <line x1="2" y1="12" x2="22" y2="12" />
  </svg>
);

const isTauri = typeof window !== "undefined" && "__TAURI__" in window;

interface Face {
  face_id: string;
  video_id: string;
  frame_id: string;
  timestamp_ms: number;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  confidence: number;
  crop_path: string | null;
  age: number | null;
  gender: string | null;
  person_id: string | null;
  person_name: string | null;
  cluster_id: string | null;
  created_at_ms: number;
}

interface Person {
  person_id: string;
  name: string;
  face_count: number;
  thumbnail_face_id: string | null;
  thumbnail_crop_path: string | null;
  created_at_ms: number;
  updated_at_ms: number;
}

interface FaceCluster {
  cluster_id: string;
  face_count: number;
  sample_faces: Face[];
}

interface FaceStats {
  total_faces: number;
  assigned_faces: number;
  unassigned_faces: number;
  total_persons: number;
  unique_clusters: number;
  videos_with_faces: number;
}

interface FaceAppearance {
  timestamp_ms: number;
  face_id: string;
  crop_path: string | null;
  confidence: number;
}

interface VideoAppearance {
  video_id: string;
  filename: string;
  duration_ms: number | null;
  thumbnail_path: string | null;
  appearances: FaceAppearance[];
  first_appearance_ms: number;
  last_appearance_ms: number;
  appearance_count: number;
}

interface PersonTimeline {
  person_id: string;
  person_name: string;
  total_appearances: number;
  videos: VideoAppearance[];
}

type ViewMode = "people" | "unassigned" | "all";

export function Faces() {
  const [viewMode, setViewMode] = useState<ViewMode>("people");
  const [faces, setFaces] = useState<Face[]>([]);
  const [persons, setPersons] = useState<Person[]>([]);
  const [clusters, setClusters] = useState<FaceCluster[]>([]);
  const [stats, setStats] = useState<FaceStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedFaces, setSelectedFaces] = useState<Set<string>>(new Set());
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState<string>("");
  const [showNameModal, setShowNameModal] = useState(false);
  const [newPersonName, setNewPersonName] = useState("");
  const [isCreatingPerson, setIsCreatingPerson] = useState(false);
  const [timeline, setTimeline] = useState<PersonTimeline | null>(null);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [favoritePersonIds, setFavoritePersonIds] = useState<Set<string>>(new Set());
  const [selectedPersonIds, setSelectedPersonIds] = useState<Set<string>>(new Set());

  // Fetch API base URL
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

  // Fetch data based on view mode
  useEffect(() => {
    fetchStats();
    fetchPersons();
    fetchClusters();
    if (viewMode === "all") {
      fetchFaces();
    }
  }, [viewMode]);

  // Fetch faces when person is selected
  useEffect(() => {
    if (selectedPerson) {
      fetchFaces(selectedPerson.person_id);
    }
  }, [selectedPerson]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("gaze.personFavorites");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setFavoritePersonIds(new Set(parsed));
        }
      } catch {
        setFavoritePersonIds(new Set());
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      "gaze.personFavorites",
      JSON.stringify(Array.from(favoritePersonIds))
    );
  }, [favoritePersonIds]);

  useEffect(() => {
    if (viewMode === "people") {
      fetchPersons();
    }
  }, [searchQuery]);

  const fetchStats = async () => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<FaceStats>("/faces/stats");
      setStats(data);
    } catch (err) {
      console.error("Failed to fetch face stats:", err);
    }
  };

  const fetchFaces = async (personId?: string) => {
    setLoading(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      let endpoint = "/faces?limit=200";

      if (personId) {
        endpoint += `&person_id=${encodeURIComponent(personId)}`;
      } else if (viewMode === "unassigned") {
        endpoint += "&unassigned=true";
      }

      const data = await apiRequest<{ faces: Face[]; total: number }>(endpoint);
      setFaces(data.faces || []);
    } catch (err) {
      console.error("Failed to fetch faces:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchPersons = async () => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const endpoint = searchQuery
        ? `/faces/persons?search=${encodeURIComponent(searchQuery)}`
        : "/faces/persons";
      const data = await apiRequest<{ persons: Person[]; total: number }>(endpoint);
      setPersons(data.persons || []);
    } catch (err) {
      console.error("Failed to fetch persons:", err);
    }
  };

  const fetchClusters = async () => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ clusters: FaceCluster[]; total: number }>(
        "/faces/cluster",
        { method: "POST", body: JSON.stringify({ threshold: 0.6 }) }
      );
      setClusters(data.clusters || []);
    } catch (err) {
      console.error("Failed to fetch clusters:", err);
    }
  };

  const resolveFaceUrl = useCallback(
    (path?: string | null) => {
      if (!path) return "";
      if (isTauri) {
        return convertFileSrc(path);
      }
      if (!apiBaseUrl) return "";
      return `${apiBaseUrl}/assets/face?path=${encodeURIComponent(path)}`;
    },
    [apiBaseUrl]
  );

  const toggleFaceSelection = (faceId: string) => {
    setSelectedFaces((prev) => {
      const next = new Set(prev);
      if (next.has(faceId)) {
        next.delete(faceId);
      } else {
        next.add(faceId);
      }
      return next;
    });
  };

  const openNameModal = (faceIds: string[]) => {
    setSelectedFaces(new Set(faceIds));
    setNewPersonName("");
    setShowNameModal(true);
  };

  const toggleFavorite = (personId: string) => {
    setFavoritePersonIds((prev) => {
      const next = new Set(prev);
      if (next.has(personId)) {
        next.delete(personId);
      } else {
        next.add(personId);
      }
      return next;
    });
  };

  const togglePersonSelection = (personId: string) => {
    setSelectedPersonIds((prev) => {
      const next = new Set(prev);
      if (next.has(personId)) {
        next.delete(personId);
      } else {
        next.add(personId);
      }
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedPersonIds(new Set());
  };

  const handleDeleteSelected = async () => {
    if (selectedPersonIds.size === 0) return;
    const confirmed = window.confirm(
      `Delete ${selectedPersonIds.size} person${selectedPersonIds.size !== 1 ? "s" : ""}? Faces will be unassigned.`
    );
    if (!confirmed) return;
    try {
      const { apiRequest } = await import("../lib/apiClient");
      for (const personId of selectedPersonIds) {
        await apiRequest(`/faces/persons/${personId}?unassign_faces=true`, { method: "DELETE" });
      }
      await fetchStats();
      await fetchPersons();
      clearSelection();
    } catch (err) {
      console.error("Failed to delete persons:", err);
      alert("Failed to delete selected people.");
    }
  };

  const handleMergeSelected = async () => {
    if (selectedPersonIds.size < 2) return;
    const ids = Array.from(selectedPersonIds);
    const primaryId = ids[0];
    const confirmed = window.confirm(
      `Merge ${ids.length} people into the first selected person?`
    );
    if (!confirmed) return;

    try {
      const { apiRequest } = await import("../lib/apiClient");
      for (const personId of ids.slice(1)) {
        const data = await apiRequest<{ faces: Face[]; total: number }>(
          `/faces?person_id=${encodeURIComponent(personId)}&limit=1000`
        );
        for (const face of data.faces || []) {
          await apiRequest(`/faces/${face.face_id}/assign`, {
            method: "POST",
            body: JSON.stringify({ person_id: primaryId }),
          });
        }
        await apiRequest(`/faces/persons/${personId}?unassign_faces=true`, { method: "DELETE" });
      }
      await fetchStats();
      await fetchPersons();
      clearSelection();
    } catch (err) {
      console.error("Failed to merge people:", err);
      alert("Failed to merge selected people.");
    }
  };

  const handleNameCluster = async (clusterId: string) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ faces: Face[]; total: number }>(
        `/faces?cluster_id=${encodeURIComponent(clusterId)}&limit=1000`
      );
      const faceIds = (data.faces || []).map((face) => face.face_id);
      if (faceIds.length === 0) return;
      openNameModal(faceIds);
    } catch (err) {
      console.error("Failed to load cluster faces:", err);
    }
  };

  const selectAllFaces = () => {
    if (selectedFaces.size === faces.length) {
      setSelectedFaces(new Set());
    } else {
      setSelectedFaces(new Set(faces.map((f) => f.face_id)));
    }
  };

  const handleCreatePerson = async () => {
    if (!newPersonName.trim() || selectedFaces.size === 0) return;

    setIsCreatingPerson(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      await apiRequest<Person>("/faces/persons", {
        method: "POST",
        body: JSON.stringify({
          name: newPersonName.trim(),
          face_ids: Array.from(selectedFaces),
        }),
      });

      // Reset state
      setShowNameModal(false);
      setNewPersonName("");
      setSelectedFaces(new Set());

      // Refresh data
      await fetchStats();
      await fetchPersons();
      await fetchClusters();
      if (viewMode === "unassigned" || viewMode === "all") {
        await fetchFaces();
      }
    } catch (err) {
      console.error("Failed to create person:", err);
      alert("Failed to create person. Please try again.");
    } finally {
      setIsCreatingPerson(false);
    }
  };

  const handleAssignToPerson = async (personId: string) => {
    if (selectedFaces.size === 0) return;

    try {
      const { apiRequest } = await import("../lib/apiClient");

      // Assign each selected face
      for (const faceId of selectedFaces) {
        await apiRequest(`/faces/${faceId}/assign`, {
          method: "POST",
          body: JSON.stringify({ person_id: personId }),
        });
      }

      // Reset and refresh
      setSelectedFaces(new Set());
      await fetchStats();
      await fetchPersons();
      await fetchClusters();
      await fetchFaces();
    } catch (err) {
      console.error("Failed to assign faces:", err);
      alert("Failed to assign faces. Please try again.");
    }
  };

  const filteredPersons = useMemo(() => {
    if (!searchQuery) return persons;
    const query = searchQuery.toLowerCase();
    return persons.filter((p) => p.name.toLowerCase().includes(query));
  }, [persons, searchQuery]);

  const favoritePersons = useMemo(() => {
    return filteredPersons.filter((person) => favoritePersonIds.has(person.person_id));
  }, [filteredPersons, favoritePersonIds]);

  const nonFavoritePersons = useMemo(() => {
    return filteredPersons.filter((person) => !favoritePersonIds.has(person.person_id));
  }, [filteredPersons, favoritePersonIds]);

  const fetchTimeline = async (personId: string) => {
    setTimelineLoading(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<PersonTimeline>(`/faces/persons/${personId}/timeline`);
      setTimeline(data);
      setShowTimeline(true);
    } catch (err) {
      console.error("Failed to fetch timeline:", err);
    } finally {
      setTimelineLoading(false);
    }
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

  const formatDuration = (ms?: number | null) => {
    if (!ms) return "--:--";
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  return (
    <div className="faces-view">
      {/* Header */}
      <div className="faces-header">
        <div className="faces-title">
          <UsersIcon />
          <div>
            <h2>People</h2>
            <span className="faces-subtitle">Runs locally on this device</span>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="faces-stats">
            <div className="stat">
              <span className="stat-value">{stats.total_faces}</span>
              <span className="stat-label">Faces</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats.total_persons}</span>
              <span className="stat-label">People</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats.unassigned_faces}</span>
              <span className="stat-label">Unassigned</span>
            </div>
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div className="faces-toolbar">
        <div className="view-tabs">
          <button
            className={`tab ${viewMode === "people" ? "active" : ""}`}
            onClick={() => {
              setViewMode("people");
              setSelectedPerson(null);
            }}
          >
            <UsersIcon />
            People
          </button>
          <button
            className={`tab ${viewMode === "unassigned" ? "active" : ""}`}
            onClick={() => {
              setViewMode("unassigned");
              setSelectedPerson(null);
            }}
          >
            <UserIcon />
            Review Unassigned
          </button>
          <button
            className={`tab ${viewMode === "all" ? "active" : ""}`}
            onClick={() => {
              setViewMode("all");
              setSelectedPerson(null);
            }}
          >
            <GridIcon />
            All Faces
          </button>
        </div>

        <div className="toolbar-actions">
          {viewMode === "people" && (
            <div className="search-box">
              <SearchIcon />
              <input
                type="text"
                placeholder="Search people..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          )}

          {selectedFaces.size > 0 && (
            <div className="selection-actions">
              <span className="selection-count">
                {selectedFaces.size} selected
              </span>
              <button
                className="btn btn-primary"
                onClick={() => setShowNameModal(true)}
              >
                <PlusIcon />
                Create Person
              </button>
              {persons.length > 0 && (
                <select
                  className="assign-select"
                  onChange={(e) => {
                    if (e.target.value) {
                      handleAssignToPerson(e.target.value);
                      e.target.value = "";
                    }
                  }}
                  defaultValue=""
                >
                  <option value="" disabled>
                    Assign to...
                  </option>
                  {persons.map((p) => (
                    <option key={p.person_id} value={p.person_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              )}
              <button
                className="btn btn-ghost"
                onClick={() => setSelectedFaces(new Set())}
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="faces-content">
        {loading ? (
          <div className="loading-state">
            <div className="spinner spinner-large" />
            <p>Loading...</p>
          </div>
        ) : viewMode === "people" ? (
          <div className="faces-people-view">
            {selectedPersonIds.size > 0 && (
              <div className="faces-section">
                <div className="faces-selection-bar">
                  <div className="faces-selection-left">
                    <span className="selection-count">
                      {selectedPersonIds.size} selected
                    </span>
                    <button className="btn btn-ghost" onClick={clearSelection}>
                      Clear
                    </button>
                  </div>
                  <div className="faces-selection-actions">
                    <button
                      className="btn btn-secondary"
                      onClick={handleMergeSelected}
                      disabled={selectedPersonIds.size < 2}
                    >
                      Merge
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={handleDeleteSelected}
                      disabled={selectedPersonIds.size === 0}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div className="faces-section">
              <div className="faces-section-header">
                <div>
                  <h3>FAVORITES</h3>
                  <p>Your most important people, pinned here.</p>
                </div>
              </div>
              {favoritePersons.length === 0 ? (
                <div className="empty-state compact">
                  <StarIcon />
                  <h3>No favorites yet</h3>
                  <p>Tap the star on a person to pin them here.</p>
                </div>
              ) : (
                <div className="persons-grid">
                  {favoritePersons.map((person) => (
                    <div
                      key={person.person_id}
                      className="person-card"
                    >
                      <div
                        className="person-card-main"
                        onClick={() => {
                          setSelectedPerson(person);
                          fetchFaces(person.person_id);
                        }}
                      >
                        <div className="person-thumbnail">
                          {person.thumbnail_crop_path ? (
                            <img
                              src={resolveFaceUrl(person.thumbnail_crop_path)}
                              alt={person.name}
                            />
                          ) : (
                            <div className="placeholder">
                              <UserIcon />
                            </div>
                          )}
                        </div>
                        <div className="person-info">
                          <div className="person-name">{person.name}</div>
                          <div className="person-meta">{person.face_count} faces</div>
                        </div>
                        <button
                          className={`person-select ${selectedPersonIds.has(person.person_id) ? "active" : ""}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            togglePersonSelection(person.person_id);
                          }}
                          title="Select"
                          type="button"
                        >
                          <CheckIcon />
                        </button>
                      </div>
                      <button
                        className={`btn-icon person-favorite ${favoritePersonIds.has(person.person_id) ? "active" : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(person.person_id);
                        }}
                        title="Toggle favorite"
                      >
                        <StarIcon filled={favoritePersonIds.has(person.person_id)} />
                      </button>
                      <button
                        className="btn-icon timeline-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          fetchTimeline(person.person_id);
                        }}
                        title="View timeline"
                      >
                        <ClockIcon />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="faces-section">
              <div className="faces-section-header">
                <div>
                  <h3>PEOPLE</h3>
                  <p>Tap a person to see everywhere they appear.</p>
                </div>
              </div>
              <div className="persons-grid">
                {nonFavoritePersons.length === 0 ? (
                  <div className="empty-state">
                    <UsersIcon />
                    <h3>No people yet</h3>
                    <p>
                      Name a few faces to get started.
                    </p>
                  </div>
                ) : (
                  nonFavoritePersons.map((person) => (
                    <div
                      key={person.person_id}
                      className="person-card"
                    >
                      <div
                        className="person-card-main"
                        onClick={() => {
                          setSelectedPerson(person);
                          fetchFaces(person.person_id);
                        }}
                      >
                        <div className="person-thumbnail">
                          {person.thumbnail_crop_path ? (
                            <img
                              src={resolveFaceUrl(person.thumbnail_crop_path)}
                              alt={person.name}
                            />
                          ) : (
                            <div className="placeholder">
                              <UserIcon />
                            </div>
                          )}
                        </div>
                        <div className="person-info">
                          <div className="person-name">{person.name}</div>
                          <div className="person-meta">{person.face_count} faces</div>
                        </div>
                        <button
                          className={`person-select ${selectedPersonIds.has(person.person_id) ? "active" : ""}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            togglePersonSelection(person.person_id);
                          }}
                          title="Select"
                          type="button"
                        >
                          <CheckIcon />
                        </button>
                      </div>
                      <button
                        className={`btn-icon person-favorite ${favoritePersonIds.has(person.person_id) ? "active" : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(person.person_id);
                        }}
                        title="Toggle favorite"
                      >
                        <StarIcon filled={favoritePersonIds.has(person.person_id)} />
                      </button>
                      <button
                        className="btn-icon timeline-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          fetchTimeline(person.person_id);
                        }}
                        title="View timeline"
                      >
                        <ClockIcon />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : viewMode === "unassigned" ? (
          <div className="clusters-grid">
            {clusters.length === 0 ? (
              <div className="empty-state">
                <UserIcon />
                <h3>No unassigned faces</h3>
                <p>You're all caught up.</p>
              </div>
            ) : (
              clusters.map((cluster) => (
                <div key={cluster.cluster_id} className="cluster-card">
                  <div className="cluster-faces">
                    {cluster.sample_faces.slice(0, 4).map((face) => (
                      <div key={face.face_id} className="cluster-face">
                        {face.crop_path ? (
                          <img src={resolveFaceUrl(face.crop_path)} alt="" />
                        ) : (
                          <div className="placeholder">
                            <UserIcon />
                          </div>
                        )}
                      </div>
                    ))}
                    {cluster.face_count > 4 && (
                      <div className="cluster-more">+{cluster.face_count - 4}</div>
                    )}
                  </div>
                  <div className="cluster-info">
                    <div className="cluster-count">{cluster.face_count} faces</div>
                    <button
                      className="btn btn-small"
                      onClick={() => handleNameCluster(cluster.cluster_id)}
                    >
                      Name
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          /* Faces Grid */
          <div className="faces-grid">
            {selectedPerson && (
              <div className="person-header">
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    setSelectedPerson(null);
                    setViewMode("persons");
                  }}
                >
                  <CloseIcon />
                  Back to People
                </button>
                <h3>{selectedPerson.name}</h3>
                <span className="face-count">{faces.length} faces</span>
              </div>
            )}

            {faces.length === 0 ? (
              <div className="empty-state">
                <UserIcon />
                <h3>No faces found</h3>
                <p>
                  {viewMode === "unassigned"
                    ? "All faces have been assigned to people."
                    : "Index some videos to detect faces."}
                </p>
              </div>
            ) : (
              <>
                <div className="select-all-row">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={selectedFaces.size === faces.length && faces.length > 0}
                      onChange={selectAllFaces}
                    />
                    Select All ({faces.length})
                  </label>
                </div>
                <div className="faces-grid-inner">
                  {faces.map((face) => (
                    <div
                      key={face.face_id}
                      className={`face-card ${selectedFaces.has(face.face_id) ? "selected" : ""}`}
                      onClick={() => toggleFaceSelection(face.face_id)}
                    >
                      <div className="face-thumbnail">
                        {face.crop_path ? (
                          <img src={resolveFaceUrl(face.crop_path)} alt="" />
                        ) : (
                          <div className="placeholder">
                            <UserIcon />
                          </div>
                        )}
                        <div className="face-checkbox">
                          {selectedFaces.has(face.face_id) && <CheckIcon />}
                        </div>
                      </div>
                      <div className="face-info">
                        {face.person_name ? (
                          <span className="face-person">{face.person_name}</span>
                        ) : (
                          <span className="face-unknown">Unknown</span>
                        )}
                        {face.confidence && (
                          <span className="face-confidence">
                            {(face.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Name Modal */}
      {showNameModal && (
        <div className="modal-overlay" onClick={() => setShowNameModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Name this person</h3>
              <button
                className="btn-icon"
                onClick={() => setShowNameModal(false)}
              >
                <CloseIcon />
              </button>
            </div>
            <div className="modal-body">
              <p>
                You're naming {selectedFaces.size} face
                {selectedFaces.size !== 1 ? "s" : ""}.
              </p>
              <input
                type="text"
                className="name-input"
                placeholder="Enter name..."
                value={newPersonName}
                onChange={(e) => setNewPersonName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handleCreatePerson();
                  }
                }}
                autoFocus
              />
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-ghost"
                onClick={() => setShowNameModal(false)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreatePerson}
                disabled={!newPersonName.trim() || isCreatingPerson}
              >
                {isCreatingPerson ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Timeline Modal */}
      {(showTimeline || timelineLoading) && (
        <div className="modal-overlay" onClick={() => { setShowTimeline(false); setTimeline(null); }}>
          <div className="timeline-modal" onClick={(e) => e.stopPropagation()}>
            <div className="timeline-header">
              <div className="timeline-title">
                <ClockIcon />
                <h3>{timeline?.person_name || "Loading..."} - Timeline</h3>
              </div>
              <button
                className="btn-icon"
                onClick={() => { setShowTimeline(false); setTimeline(null); }}
              >
                <CloseIcon />
              </button>
            </div>
            <div className="timeline-body">
              {timelineLoading ? (
                <div className="loading-state">
                  <div className="spinner spinner-large" />
                  <p>Loading timeline...</p>
                </div>
              ) : timeline ? (
                <>
                  <div className="timeline-summary">
                    <div className="timeline-stat">
                      <span className="stat-value">{timeline.total_appearances}</span>
                      <span className="stat-label">Appearances</span>
                    </div>
                    <div className="timeline-stat">
                      <span className="stat-value">{timeline.videos.length}</span>
                      <span className="stat-label">Videos</span>
                    </div>
                  </div>
                  <div className="timeline-videos">
                    {timeline.videos.map((video) => (
                      <div key={video.video_id} className="timeline-video">
                        <div className="timeline-video-header">
                          <div className="timeline-video-thumb">
                            {video.thumbnail_path ? (
                              <img
                                src={resolveFaceUrl(video.thumbnail_path)}
                                alt=""
                              />
                            ) : (
                              <div className="placeholder">
                                <FilmIcon />
                              </div>
                            )}
                          </div>
                          <div className="timeline-video-info">
                            <div className="timeline-video-name">{video.filename}</div>
                            <div className="timeline-video-meta">
                              {video.appearance_count} appearance{video.appearance_count !== 1 ? "s" : ""} &bull;
                              {" "}{formatTimestamp(video.first_appearance_ms)} - {formatTimestamp(video.last_appearance_ms)}
                              {video.duration_ms && ` / ${formatDuration(video.duration_ms)}`}
                            </div>
                          </div>
                        </div>
                        <div className="timeline-appearances">
                          {video.appearances.slice(0, 12).map((appearance, idx) => (
                            <div key={`${appearance.face_id}-${idx}`} className="timeline-appearance">
                              <div className="timeline-face-thumb">
                                {appearance.crop_path ? (
                                  <img src={resolveFaceUrl(appearance.crop_path)} alt="" />
                                ) : (
                                  <div className="placeholder">
                                    <UserIcon />
                                  </div>
                                )}
                              </div>
                              <span className="timeline-timestamp">
                                {formatTimestamp(appearance.timestamp_ms)}
                              </span>
                            </div>
                          ))}
                          {video.appearances.length > 12 && (
                            <div className="timeline-more">
                              +{video.appearances.length - 12} more
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <UserIcon />
                  <h3>No appearances found</h3>
                  <p>This person hasn't been detected in any videos yet.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

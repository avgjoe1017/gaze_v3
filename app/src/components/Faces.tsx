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

const TagIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
    <line x1="7" y1="7" x2="7.01" y2="7" />
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

const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
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

type ViewMode = "all" | "persons" | "unassigned" | "clusters";

export function Faces() {
  const [viewMode, setViewMode] = useState<ViewMode>("all");
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
  const [isClustering, setIsClustering] = useState(false);
  const [timeline, setTimeline] = useState<PersonTimeline | null>(null);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);

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
    if (viewMode === "all" || viewMode === "unassigned") {
      fetchFaces();
    } else if (viewMode === "persons") {
      fetchPersons();
    } else if (viewMode === "clusters") {
      fetchClusters();
    }
  }, [viewMode]);

  // Fetch faces when person is selected
  useEffect(() => {
    if (selectedPerson) {
      fetchFaces(selectedPerson.person_id);
    }
  }, [selectedPerson]);

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
    setLoading(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const endpoint = searchQuery
        ? `/faces/persons?search=${encodeURIComponent(searchQuery)}`
        : "/faces/persons";
      const data = await apiRequest<{ persons: Person[]; total: number }>(endpoint);
      setPersons(data.persons || []);
    } catch (err) {
      console.error("Failed to fetch persons:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchClusters = async () => {
    setLoading(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ clusters: FaceCluster[]; total: number }>(
        "/faces/cluster",
        { method: "POST", body: JSON.stringify({ threshold: 0.6 }) }
      );
      setClusters(data.clusters || []);
    } catch (err) {
      console.error("Failed to fetch clusters:", err);
    } finally {
      setLoading(false);
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
      if (viewMode === "persons") {
        await fetchPersons();
      } else {
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
      await fetchFaces();
    } catch (err) {
      console.error("Failed to assign faces:", err);
      alert("Failed to assign faces. Please try again.");
    }
  };

  const handleMergeFaces = async (clusterId: string) => {
    try {
      const { apiRequest } = await import("../lib/apiClient");

      // Get faces in this cluster
      const clusterFaces = clusters.find((c) => c.cluster_id === clusterId)?.sample_faces || [];

      // Create a new person from this cluster
      await apiRequest("/faces/merge", {
        method: "POST",
        body: JSON.stringify({
          face_ids: clusterFaces.map((f) => f.face_id),
          name: `Person (Cluster ${clusterId})`,
        }),
      });

      // Refresh
      await fetchStats();
      await fetchClusters();
    } catch (err) {
      console.error("Failed to merge faces:", err);
      alert("Failed to merge faces. Please try again.");
    }
  };

  const handleRunClustering = async () => {
    setIsClustering(true);
    try {
      const { apiRequest } = await import("../lib/apiClient");
      const data = await apiRequest<{ clusters: FaceCluster[]; total: number }>(
        "/faces/cluster",
        { method: "POST", body: JSON.stringify({ threshold: 0.6 }) }
      );
      setClusters(data.clusters || []);
      await fetchStats();
    } catch (err) {
      console.error("Failed to run clustering:", err);
      alert("Failed to run clustering. Please try again.");
    } finally {
      setIsClustering(false);
    }
  };

  const filteredPersons = useMemo(() => {
    if (!searchQuery) return persons;
    const query = searchQuery.toLowerCase();
    return persons.filter((p) => p.name.toLowerCase().includes(query));
  }, [persons, searchQuery]);

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
          <h2>Face Recognition</h2>
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
            className={`tab ${viewMode === "all" ? "active" : ""}`}
            onClick={() => {
              setViewMode("all");
              setSelectedPerson(null);
            }}
          >
            <GridIcon />
            All Faces
          </button>
          <button
            className={`tab ${viewMode === "persons" ? "active" : ""}`}
            onClick={() => {
              setViewMode("persons");
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
            Unassigned
          </button>
          <button
            className={`tab ${viewMode === "clusters" ? "active" : ""}`}
            onClick={() => {
              setViewMode("clusters");
              setSelectedPerson(null);
            }}
          >
            <TagIcon />
            Clusters
          </button>
        </div>

        <div className="toolbar-actions">
          {viewMode === "persons" && (
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

          {viewMode === "clusters" && (
            <button
              className="btn btn-secondary"
              onClick={handleRunClustering}
              disabled={isClustering}
            >
              {isClustering ? (
                <>
                  <div className="spinner" style={{ width: 16, height: 16 }} />
                  Clustering...
                </>
              ) : (
                <>
                  <RefreshIcon />
                  Re-cluster
                </>
              )}
            </button>
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
        ) : viewMode === "persons" && !selectedPerson ? (
          /* Persons Grid */
          <div className="persons-grid">
            {filteredPersons.length === 0 ? (
              <div className="empty-state">
                <UsersIcon />
                <h3>No people yet</h3>
                <p>
                  Select faces from the "All Faces" or "Unassigned" tabs and create people.
                </p>
              </div>
            ) : (
              filteredPersons.map((person) => (
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
                  </div>
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
        ) : viewMode === "clusters" ? (
          /* Clusters Grid */
          <div className="clusters-grid">
            {clusters.length === 0 ? (
              <div className="empty-state">
                <TagIcon />
                <h3>No clusters</h3>
                <p>
                  Click "Re-cluster" to automatically group similar faces together.
                </p>
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
                      onClick={() => handleMergeFaces(cluster.cluster_id)}
                    >
                      Create Person
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
              <h3>Create Person</h3>
              <button
                className="btn-icon"
                onClick={() => setShowNameModal(false)}
              >
                <CloseIcon />
              </button>
            </div>
            <div className="modal-body">
              <p>
                Creating a person with {selectedFaces.size} face
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

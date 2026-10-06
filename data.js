window.loadFootballSnapshot = async function () {
  if (window.location.protocol === "file:") return { isLive: false };
  try {
    const response = await fetch("./data/football.json", { cache: "no-cache" });
    if (!response.ok) return { isLive: false };
    const snapshot = await response.json();
    const expectedKeys = ["premier", "laliga", "bundesliga", "seriea", "ligue1"];
    const snapshotKeys = Object.keys(snapshot.competitions || {});
    const validCompetitions = expectedKeys.every((key) => {
      const competition = snapshot.competitions?.[key];
      return competition && Array.isArray(competition.teams) && Array.isArray(competition.matches) && Array.isArray(competition.scorers);
    });
    if (snapshot.schemaVersion !== 1 || !expectedKeys.every((key) => snapshotKeys.includes(key)) || !validCompetitions) {
      return { isLive: false };
    }
    return {
      competitions: snapshot.competitions,
      isLive: true,
      generatedAt: snapshot.generatedAt,
      date: snapshot.date,
      source: snapshot.source
    };
  } catch {
    return { isLive: false };
  }
};

window.loadFootballSnapshot = async function (fallbackCompetitions) {
  if (window.location.protocol === "file:") {
    return { competitions: fallbackCompetitions, isLive: false };
  }

  try {
    const response = await fetch("./data/football.json", { cache: "no-cache" });
    if (!response.ok) return { competitions: fallbackCompetitions, isLive: false };

    const snapshot = await response.json();
    const expectedKeys = Object.keys(fallbackCompetitions);
    const snapshotKeys = Object.keys(snapshot.competitions || {});
    if (snapshot.schemaVersion !== 1 || !expectedKeys.every((key) => snapshotKeys.includes(key))) {
      return { competitions: fallbackCompetitions, isLive: false };
    }

    return {
      competitions: snapshot.competitions,
      isLive: true,
      generatedAt: snapshot.generatedAt,
      date: snapshot.date,
      source: snapshot.source
    };
  } catch {
    return { competitions: fallbackCompetitions, isLive: false };
  }
};

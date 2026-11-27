(() => {
  const status = document.querySelector("[data-connection-status]");
  const installButton = document.querySelector("[data-install-app]");
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  let installPrompt = null;

  function updateStatus() {
    if (!status) return;
    status.textContent = navigator.onLine ? "En ligne" : "Hors ligne";
    status.dataset.state = navigator.onLine ? "online" : "offline";
  }
  window.addEventListener("online", updateStatus);
  window.addEventListener("offline", updateStatus);
  updateStatus();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch((error) => {
        console.error("Service worker registration failed", error);
      });
    });
  }

  if (installButton && isIOS && !isStandalone) {
    installButton.hidden = false;
    installButton.textContent = "Installer sur iPhone";
    installButton.addEventListener("click", () => {
      alert("Sur iPhone : touchez le bouton Partager de Safari, puis « Sur l’écran d’accueil », et enfin « Ajouter ».");
    });
  }

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    if (installButton && !isIOS) installButton.hidden = false;
  });

  if (installButton && !isIOS) {
    installButton.addEventListener("click", async () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      installButton.hidden = true;
    });
  }

  window.addEventListener("appinstalled", () => {
    if (installButton) installButton.hidden = true;
  });
})();

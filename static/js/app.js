// Visionneuse d'images : un clic sur une image [data-zoom] l'ouvre en grand.
document.addEventListener("click", function (e) {
  var img = e.target.closest("[data-zoom]");
  var modale = document.getElementById("visionneuse");
  if (!img || !modale || !window.bootstrap) return;
  modale.querySelector("img").src = img.getAttribute("data-zoom") || img.src;
  modale.querySelector("img").alt = img.alt || "";
  window.bootstrap.Modal.getOrCreateInstance(modale).show();
});

// Information sur les cookies : affichée une fois, mémorisée dans le navigateur.
(function () {
  var bandeau = document.getElementById("bandeau-cookies");
  if (!bandeau) return;
  var vu = false;
  try { vu = window.localStorage.getItem("fs_cookies_ok") === "1"; } catch (e) {}
  if (!vu) bandeau.hidden = false;
  var bouton = document.getElementById("cookies-ok");
  if (bouton) bouton.addEventListener("click", function () {
    bandeau.hidden = true;
    try { window.localStorage.setItem("fs_cookies_ok", "1"); } catch (e) {}
  });
})();

// Aplica tamaño de letra y tema antes de pintar, para no mostrar un destello con otro tamaño.
// Archivo aparte (no en línea) porque la política de seguridad del servidor bloquea scripts en línea.
try {
  var t = localStorage.getItem("jacomind.tamano"), c = localStorage.getItem("jacomind.tema") || "claro";
  if (t) document.documentElement.dataset.tamano = t;
  if (c === "oscuro") document.documentElement.dataset.theme = "dark";
  else if (c === "sistema") delete document.documentElement.dataset.theme;
} catch (e) { /* sin almacenamiento */ }

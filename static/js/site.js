const navToggle = document.querySelector(".nav-toggle");
const navigation = document.querySelector("#primary-nav");

if (navToggle && navigation) {
  navToggle.addEventListener("click", () => {
    const expanded = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!expanded));
    navigation.classList.toggle("nav-open", !expanded);
  });
  navigation.addEventListener("click", (event) => {
    if (event.target instanceof HTMLAnchorElement) {
      navToggle.setAttribute("aria-expanded", "false");
      navigation.classList.remove("nav-open");
    }
  });
}

document.querySelectorAll(".flash").forEach((flash) => {
  window.setTimeout(() => {
    flash.classList.add("flash-dismissed");
    window.setTimeout(() => flash.remove(), 300);
  }, 6500);
});

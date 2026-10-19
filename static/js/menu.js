const searchInput = document.querySelector("#menu-search");
const filterButtons = [...document.querySelectorAll("[data-category-filter]")];
const cards = [...document.querySelectorAll("[data-product-card]")];
const emptyState = document.querySelector("#menu-empty");
let activeCategory = "all";

function filterMenu() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const card of cards) {
    const matchesCategory = activeCategory === "all" || card.dataset.category === activeCategory;
    const matchesQuery = card.dataset.search.includes(query);
    card.hidden = !(matchesCategory && matchesQuery);
    if (!card.hidden) visible += 1;
  }
  emptyState.hidden = visible > 0;
}

if (searchInput) {
  searchInput.addEventListener("input", filterMenu);
  const initialQuery = searchInput.value.trim().toLocaleLowerCase();
  if (initialQuery) filterMenu();
}
for (const button of filterButtons) {
  button.addEventListener("click", () => {
    activeCategory = button.dataset.categoryFilter;
    for (const filterButton of filterButtons) {
      const selected = filterButton === button;
      filterButton.classList.toggle("active", selected);
      filterButton.setAttribute("aria-pressed", String(selected));
    }
    filterMenu();
  });
  button.setAttribute("aria-pressed", String(button.dataset.categoryFilter === activeCategory));
}

const dialog = document.querySelector("#product-dialog");
const dialogClose = dialog?.querySelector(".dialog-close");
for (const trigger of document.querySelectorAll("[data-product-modal]")) {
  trigger.addEventListener("click", () => {
    const data = trigger.parentElement.querySelector(".product-modal-data");
    const name = data.dataset.name;
    dialog.querySelector("#dialog-title").textContent = name;
    dialog.querySelector(".dialog-description").textContent = data.dataset.description;
    dialog.querySelector(".dialog-price").textContent = data.dataset.price;
    dialog.querySelector(".dialog-allergens").textContent = data.dataset.allergens
      ? `Allergens (as supplied): ${data.dataset.allergens}`
      : "Allergen information has not been supplied.";
    const art = dialog.querySelector(".dialog-art");
    art.replaceChildren();
    if (data.dataset.art.startsWith("uploads/")) {
      const image = document.createElement("img");
      image.src = `/static/${data.dataset.art}`;
      image.alt = `Cafe menu image for ${name}`;
      art.append(image);
    } else {
      art.className = `dialog-art product-art art-${data.dataset.art}`;
      const cup = document.createElement("div");
      cup.className = "drink-cup";
      const logo = document.createElement("span");
      logo.className = "drink-logo";
      logo.textContent = "t.";
      cup.append(logo);
      art.append(cup);
    }
    dialog.showModal();
  });
}
dialogClose?.addEventListener("click", () => dialog.close());
dialog?.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

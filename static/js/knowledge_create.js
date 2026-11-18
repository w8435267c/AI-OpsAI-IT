(() => {
  "use strict";

  const space = document.getElementById("id_space");
  const category = document.getElementById("id_category");
  if (!space || !category) {
    return;
  }

  function syncCategories() {
    const selectedSpace = space.value;
    let selectedCategoryIsVisible = false;
    for (const option of category.options) {
      if (!option.value) {
        continue;
      }
      const visible = Boolean(selectedSpace) && option.dataset.spaceId === selectedSpace;
      option.hidden = !visible;
      option.disabled = !visible;
      if (option.selected && visible) {
        selectedCategoryIsVisible = true;
      }
    }
    if (!selectedCategoryIsVisible) {
      category.value = "";
    }
  }

  space.addEventListener("change", syncCategories);
  syncCategories();
})();

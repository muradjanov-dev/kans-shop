import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProductGallery } from "@/components/storefront/ProductGallery";
import { renderWithProviders } from "@/test/renderWithProviders";

describe("ProductGallery", () => {
  it("shows a neutral fallback when no image URL is available", () => {
    renderWithProviders(<ProductGallery images={[{ id: 1, url: null, telegram_file_id: null, is_main: true, sort_order: 0 }]} name="Notebook" />);

    expect(screen.getByRole("img", { name: "Rasm mavjud emas" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Notebook" })).not.toBeInTheDocument();
  });

  it("shows a neutral per-image fallback after a selected image fails", () => {
    renderWithProviders(
      <ProductGallery
        images={[
          { id: 1, url: "", telegram_file_id: null, is_main: true, sort_order: 0 },
          { id: 2, url: "https://images.example/broken.jpg", telegram_file_id: null, is_main: false, sort_order: 1 },
          { id: 3, url: "https://images.example/second.jpg", telegram_file_id: null, is_main: false, sort_order: 2 },
        ]}
        name="Notebook"
      />,
    );

    const mainImage = screen.getByRole("img", { name: "Notebook" });
    expect(mainImage).toHaveAttribute("src", "https://images.example/broken.jpg");
    fireEvent.error(mainImage);
    expect(screen.getByRole("img", { name: "Rasm mavjud emas" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Rasmni tanlash 2" }));
    expect(screen.getByRole("img", { name: "Notebook" })).toHaveAttribute(
      "src",
      "https://images.example/second.jpg",
    );
  });

  it("starts on the first image URL and allows selecting another image", () => {
    renderWithProviders(
      <ProductGallery
        images={[
          { id: 1, url: null, telegram_file_id: null, is_main: true, sort_order: 0 },
          { id: 2, url: "https://images.example/first.jpg", telegram_file_id: null, is_main: false, sort_order: 1 },
          { id: 3, url: "https://images.example/second.jpg", telegram_file_id: null, is_main: false, sort_order: 2 },
        ]}
        name="Notebook"
      />,
    );

    expect(screen.getByRole("img", { name: "Notebook" })).toHaveAttribute(
      "src",
      "https://images.example/first.jpg",
    );
    fireEvent.click(screen.getByRole("button", { name: "Rasmni tanlash 2" }));
    expect(screen.getByRole("img", { name: "Notebook" })).toHaveAttribute(
      "src",
      "https://images.example/second.jpg",
    );
  });
});

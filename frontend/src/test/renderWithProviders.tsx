import { StrictMode, type ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CustomerAuthProvider } from "@/features/customer-auth/CustomerAuthProvider";

export function renderWithProviders(
  ui: ReactElement,
  initialEntry = "/",
  withCustomerAuth = false,
  strict = false,
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  const content = withCustomerAuth ? (
    <CustomerAuthProvider>{ui}</CustomerAuthProvider>
  ) : ui;
  const wrappedContent = strict ? <StrictMode>{content}</StrictMode> : content;
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{wrappedContent}</MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient };
}

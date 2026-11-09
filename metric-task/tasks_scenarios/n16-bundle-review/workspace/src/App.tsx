import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import { AssistantPage } from './routes/AssistantPage';
import { CheckoutPage } from './routes/CheckoutPage';
import { OrdersPage } from './routes/OrdersPage';
import { SettingsPage } from './routes/SettingsPage';

export function App() {
  return (
    <BrowserRouter>
      <nav className="top-nav">
        <NavLink to="/">Checkout</NavLink>
        <NavLink to="/orders">Orders</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <NavLink to="/assistant">Assistant</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<CheckoutPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
      </Routes>
    </BrowserRouter>
  );
}

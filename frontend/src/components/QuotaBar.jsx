import React, { useEffect, useState } from 'react';
import { API_BASE } from '../constants';
import { Server, AlertTriangle } from 'lucide-react';
import { toast } from '../lib/toast.jsx';

export default function QuotaBar() {
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchQuota = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/quota`);
      if (res.ok) {
        const data = await res.json();
        setQuota(data);
      }
    } catch (e) {
      toast("Lỗi lấy quota: " + e.message, { type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuota();
    const interval = setInterval(fetchQuota, 30000); // Tự động cập nhật mỗi 30s
    return () => clearInterval(interval);
  }, []);

  if (loading) return null;
  if (!quota) return null;

  let colorClass = "bg-green";
  if (quota.percent > 50) colorClass = "bg-yellow";
  if (quota.percent > 85) colorClass = "bg-red";

  return (
    <div className="quota-bar-container">
      <div className="quota-header">
        <div className="quota-title">
          <Server size={14} /> 
          <span>Gemini API Quota (Hôm nay)</span>
        </div>
        <div className="quota-text">
          {quota.used} / {quota.limit} ({quota.percent}%)
        </div>
      </div>
      
      <div className="quota-progress-bg">
        <div className={`quota-progress-fill ${colorClass}`} style={{ width: `${Math.min(quota.percent, 100)}%` }}></div>
      </div>
      
      {quota.percent > 90 && (
        <div className="quota-warning">
          <AlertTriangle size={12} />
          <span>Sắp hết dung lượng miễn phí! Vui lòng thêm Key phụ.</span>
        </div>
      )}
    </div>
  );
}

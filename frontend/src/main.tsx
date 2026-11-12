import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
type Status = {service:string;version:string;database:string;mcp:string;security:string};
function App(){
 const [status,setStatus]=useState<Status|null>(null);
 const [error,setError]=useState('');
 useEffect(()=>{fetch('/api/status').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(setStatus).catch(e=>setError(String(e)))},[]);
 return <main><header><span className="mark">✦</span><div><h1>NEXUS AI</h1><p>Secure Foundation · 0.1</p></div></header><section className="hero"><span className="eyebrow">ЦЕНТР УПРАВЛЕНИЯ</span><h2>Фундамент автономной платформы</h2><p>Локальная панель диагностики. Управление агентами и авторизация будут добавлены после проверки безопасности.</p></section><div className="grid"><article><small>Backend</small><strong>{status?.service ?? 'Ожидание'}</strong></article><article><small>PostgreSQL</small><strong>{status?.database ?? 'Нет данных'}</strong></article><article><small>MCP</small><strong>{status?.mcp ?? 'Нет данных'}</strong></article><article><small>Режим</small><strong>Только диагностика</strong></article></div>{error&&<p role="alert" className="error">Ошибка подключения: {error}</p>}<footer>Не публиковать в интернете: авторизация ещё не реализована.</footer></main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);

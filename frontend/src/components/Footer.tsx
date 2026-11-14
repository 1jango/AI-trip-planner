// Stopka widoczna zawsze — atrybucja danych to wymóg licencji (Transitous, OpenStreetMap),
// a legenda tłumaczy, które liczby są z rozkładu jazdy, a które są naszym szacunkiem.
export function Footer() {
  return (
    <footer className="footer">
      <h2 className="small-heading">Skąd są te liczby?</h2>
      <ul>
        <li>
          <strong>Połączenia</strong> (pociągi, autobusy, tramwaje, promy) — prawdziwe rozkłady
          jazdy z{' '}
          <a href="https://transitous.org/sources/" target="_blank" rel="noreferrer">
            Transitous
          </a>
          . Wyszukiwanie miejsc: ©{' '}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            współtwórcy OpenStreetMap
          </a>
          .
        </li>
        <li>
          <strong>CO₂</strong> — dystans × współczynnik emisji na pasażerokilometr z{' '}
          <a
            href="https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025"
            target="_blank"
            rel="noreferrer"
          >
            UK GHG Conversion Factors 2025 (DESNZ)
          </a>
          .
        </li>
        <li>
          <span className="badge badge-warn">Szacunek</span> — loty (dystans w linii prostej,
          średnia prędkość), etapy zmienione ręcznie i koszt. Transitous nie podaje cen biletów,
          więc koszt to orientacyjne stawki za kilometr.
        </li>
        <li>
          <strong>AI</strong> tylko odczytuje z Twojego zdania skąd, dokąd, kiedy i priorytet. Nie
          wymyśla połączeń, cen ani emisji.
        </li>
      </ul>
    </footer>
  )
}

# SolarEdge Portal Live

Intégration personnalisée Home Assistant pour lire en direct la puissance solaire, la consommation et les échanges avec le réseau depuis le portail SolarEdge.

## Installation avec HACS

Home Assistant 2026.8.2 ou ultérieur et HACS doivent être installés.

1. Ouvre **HACS → ⋮ → Dépôts personnalisés**.
2. Ajoute le [dépôt SolarEdge Portal Live](https://github.com/philippec78/SolarEdge-Portal-Live) dans la catégorie **Intégration**.
3. Dans HACS, cherche **SolarEdge Portal Live**, télécharge l’intégration et redémarre Home Assistant.
4. Dans **Paramètres → Appareils et services → Ajouter une intégration**, sélectionne **SolarEdge Portal Live**.
5. Saisis l’adresse e-mail et le mot de passe de ton compte SolarEdge, puis l’identifiant du site visible dans l’adresse du tableau de bord après `siteId=`. L’intervalle de lecture est de 30 secondes par défaut et se règle entre 15 et 120 secondes.

Entre le lever et le coucher du soleil, l’intégration utilise l’intervalle de jour configuré. La nuit, elle interroge SolarEdge toutes les 15 minutes par défaut. Pour modifier les deux intervalles, ouvre **Paramètres → Appareils et services → SolarEdge Portal Live → Configurer**. Le réglage de jour va de 15 à 120 secondes et celui de nuit de 1 à 120 minutes. Home Assistant recharge l’intégration en enregistrant ce réglage. Les horaires de lever et de coucher suivent la localisation configurée dans Home Assistant.

## Entités

| Entité | Mesure |
| --- | --- |
| Puissance réseau | Watts positifs à l’import et négatifs à l’injection |
| Puissance importée | Watts importés du réseau |
| Puissance injectée | Watts injectés sur le réseau |
| Puissance solaire | Production instantanée en watts |
| Puissance consommée | Consommation instantanée du site en watts |
| Dernier relevé | Horodatage fourni par SolarEdge |

Les capteurs de puissance deviennent indisponibles si la lecture échoue ou si SolarEdge signale une communication indisponible. Le jour, le direct est également requis. La nuit, les instantanés hors direct sont acceptés dans la limite d’âge décrite ci-dessous. Le jour, la mesure doit dater de deux minutes au maximum. La nuit, sa limite d’âge correspond à l’intervalle de nuit plus deux minutes, avec un minimum de cinq minutes. Par exemple, un intervalle de nuit de deux minutes accepte une mesure vieille de cinq minutes au maximum, et un intervalle de quinze minutes une mesure vieille de dix-sept minutes au maximum. Au lever du soleil, la limite de deux minutes s’applique à nouveau. Le capteur Dernier relevé conserve l’horodatage fourni par SolarEdge. Les attributs source_status et source_timestamp indiquent aussi le type de relevé ou le motif de rejet. Les valeurs possibles de source_status sont live, cached, stale, not_live, not_communicating et invalid_timestamp.

## Connexion SolarEdge

Home Assistant conserve le mot de passe et le jeton de renouvellement dans la configuration locale de l’intégration. Les sauvegardes de configuration peuvent les contenir. Le module renouvelle automatiquement le jeton d’accès. Si SolarEdge refuse le jeton de renouvellement, il tente une nouvelle connexion. Si le portail exige une vérification interactive, Home Assistant demande une réauthentification.

Le flux utilisé est celui du portail SolarEdge et peut évoluer. La connexion et le renouvellement ont été observés dans Firefox. L’accès avec le module reste à valider sur une instance Home Assistant connectée au compte réel. Le projet est indépendant de SolarEdge. Le parcours de connexion est également documenté dans le projet [SolarEdge Cloud](https://github.com/digital-homesteaders/ha-solaredge).

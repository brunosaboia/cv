# Bruno Saboia's CV generator
## What
This is a small pet project that helps me with the building of my CV and deploy it to my website in an automated fashion.

It reads from a single source of truth (a [JSON](https://www.json.org/json-en.html) file), and through a [Jinja2](https://jinja.palletsprojects.com/en/stable/) template, it generates a `.tex` file, which is then compiled into a CV. A [GitHub Action](https://docs.github.com/en/actions) pushes the file to my personal website on build, and then one can see my most up-to-date CV [here](https://bruno.saboia.it/cv).

## Why
I have written many versions of my CV. As a programmer, I do not like to repeat my self, so copy-pasting data from one CV standard to another seemed to be a little bit of a big re-work. My main idea is to have various CVs that I can tailor to a specific need or market. For example, in Switzerland, CVs with photos are well-received—on the other hand, in Brazil, this is frowned upon. My idea is to be able to quickly generate multiple versions of my CV if necessary. Initially, my idea was to use [LinkedIn](https://www.linkedin.com/) as a source of truth for my data, but they don't have a good API for that. Therefore, I decide to take control of my own data and make this little project.

Another big reason for doing this project is my believe that you should own your on data, so here it is :)

## Who
This project was done by Bruno Saboia de Albuquerque.

## License
This project is licensed under the [MIT License](https://license.md/licenses/mit-license/).
